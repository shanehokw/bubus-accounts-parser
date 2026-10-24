// Offline OCR for PDFs whose text is stored as images (e.g. HSBC statements).
// Uses macOS PDFKit to render each page and the Vision framework to read it.
//
// Usage: pdf_ocr <file.pdf> [password]
// Output (stdout): JSON {"pages": [{"width": w, "height": h, "lines": [{"text", "x0", "y0", "x1", "y1"}]}]}
// Coordinates are in PDF points with the origin at the top-left of the page.
//
// Vision skips small lines when given a whole page, so each page is read in
// overlapping horizontal strips. Each strip keeps only the lines whose centre falls
// in its own band (the strip minus half the overlap at each end), so every line is
// read whole, exactly once. A final whole-page pass adds anything taller than a strip.

import Foundation
import PDFKit
import Vision

struct Line: Codable { let text: String; let x0, y0, x1, y1: Double }
struct Page: Codable { let width, height: Double; let lines: [Line] }
struct Output: Codable { let pages: [Page] }

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}

let scale: CGFloat = 4.0
let stripHeight: CGFloat = 120   // points
let stripOverlap: CGFloat = 40   // points

func render(_ page: PDFPage) -> CGImage {
    let bounds = page.bounds(for: .mediaBox)
    let w = Int(bounds.width * scale), h = Int(bounds.height * scale)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { fail("cannot render page") }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    guard let image = ctx.makeImage() else { fail("cannot render page") }
    return image
}

// Reads `image`, which covers the page region starting `top` points from the top.
func recognise(_ image: CGImage, top: Double, pageWidth: Double) -> [Line] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    request.minimumTextHeight = 0
    try? VNImageRequestHandler(cgImage: image).perform([request])

    let regionHeight = Double(image.height) / Double(scale)
    return (request.results ?? []).compactMap { obs in
        guard let text = obs.topCandidates(1).first?.string else { return nil }
        let b = obs.boundingBox  // normalised, origin bottom-left
        return Line(text: text,
                    x0: Double(b.minX) * pageWidth, y0: top + Double(1 - b.maxY) * regionHeight,
                    x1: Double(b.maxX) * pageWidth, y1: top + Double(1 - b.minY) * regionHeight)
    }
}

func overlaps(_ a: Line, _ b: Line) -> Bool {
    let ox = min(a.x1, b.x1) - max(a.x0, b.x0)
    let oy = min(a.y1, b.y1) - max(a.y0, b.y0)
    guard ox > 0, oy > 0 else { return false }
    let minW = min(a.x1 - a.x0, b.x1 - b.x0), minH = min(a.y1 - a.y0, b.y1 - b.y0)
    return ox > 0.5 * minW && oy > 0.5 * minH
}

let args = CommandLine.arguments
guard args.count >= 2 else { fail("usage: pdf_ocr <file.pdf> [password]") }
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else { fail("cannot open PDF") }
if doc.isLocked {
    guard args.count >= 3, doc.unlock(withPassword: args[2]) else { fail("PASSWORD_REQUIRED") }
}

var pages: [Page] = []
for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let image = render(page)

    var lines: [Line] = []
    // Adds a line unless it overlaps one already kept (a repeat reading, or a box
    // that spans several rows); the first set of strips is read first and wins.
    func add(_ l: Line) {
        if !lines.contains(where: { overlaps($0, l) }) { lines.append(l) }
    }

    // Two sets of strips, offset from each other, as Vision occasionally misses a line.
    let step = stripHeight - stripOverlap
    for offset in [0, step / 2] {
        let tops = [CGFloat(0)] + Array(stride(from: offset == 0 ? step : offset, to: bounds.height - stripOverlap, by: step))
        for top in tops {
            let height = min(stripHeight, bounds.height - top)
            let isLast = top + height >= bounds.height
            let bandTop = Double(top == 0 ? 0 : top + stripOverlap / 2)
            let bandBottom = Double(isLast ? bounds.height : top + height - stripOverlap / 2)
            let rect = CGRect(x: 0, y: top * scale, width: CGFloat(image.width), height: height * scale)
            guard let strip = image.cropping(to: rect) else { continue }
            for l in recognise(strip, top: Double(top), pageWidth: Double(bounds.width)) {
                let centre = (l.y0 + l.y1) / 2
                if centre >= bandTop && centre < bandBottom { add(l) }
            }
        }
    }
    recognise(image, top: 0, pageWidth: Double(bounds.width)).forEach(add)

    pages.append(Page(width: Double(bounds.width), height: Double(bounds.height), lines: lines))
}

FileHandle.standardOutput.write(try JSONEncoder().encode(Output(pages: pages)))
