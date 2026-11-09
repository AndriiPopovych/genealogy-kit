import PDFKit
import AppKit

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("Помилка: " + message + "\n").utf8)); exit(1)
}
func positive(_ text: String, _ label: String) -> Int {
    guard let value = Int(text), value > 0, value <= 1000000 else { fail("\(label): потрібне ціле число 1…1000000") }; return value
}
func number(_ text: String, _ label: String) -> Double {
    guard let value = Double(text), value.isFinite, value > 0 else { fail("\(label): потрібне додатне скінченне число") }; return value
}
func writeImage(_ rep: NSBitmapImageRep, _ kind: NSBitmapImageRep.FileType, _ path: String) {
    guard let data = rep.representation(using: kind, properties: [.compressionFactor: 0.75]) else { fail("Не вдалося кодувати зображення") }
    guard !FileManager.default.fileExists(atPath: path) else { fail("Вихід уже існує; виберіть новий шлях") }
    do { try data.write(to: URL(fileURLWithPath: path), options: .atomic) } catch { fail("Не вдалося записати результат: \(error.localizedDescription)") }
}
func checkCanvas(_ width: CGFloat, _ height: CGFloat) {
    guard width.isFinite, height.isFinite, width >= 1, height >= 1, width <= 50000, height <= 50000, width * height <= 100000000 else { fail("Некоректний або завеликий растр; зменшіть масштаб/діапазон") }
}

// usage: pdfbands <pdf> <first> <last> <step> <bandFrac 0-1> <width px> <out.jpg>
// Stacks the top band (headers: year, section) of selected PDF pages, labelled with page numbers.
let a = CommandLine.arguments
guard a.count == 8 else { fail("Некоректна кількість аргументів; див. коментар використання") }
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])), doc.pageCount > 0 else { fail("PDF не відкрився або порожній") }
let first = positive(a[2], "Перша"), last = positive(a[3], "Остання"), step = positive(a[4], "Крок")
guard first <= last, last <= doc.pageCount else { fail("Діапазон поза PDF або обернений") }
let frac = CGFloat(number(a[5], "Частка")), W = CGFloat(number(a[6], "Ширина"))
guard frac <= 1 else { fail("Частка має бути в (0,1]") }
let pages = Array(stride(from: first, through: last, by: step))
let lab: CGFloat = 26
var heights: [CGFloat] = []
for p in pages { let b = doc.page(at: p-1)!.bounds(for: .mediaBox); heights.append(W * b.height / b.width * frac) }
let H = heights.reduce(0) { $0 + $1 + lab }
checkCanvas(W, H)
guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(W), pixelsHigh: Int(H), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { fail("Не вистачило пам’яті для растра") }
NSGraphicsContext.saveGraphicsState()
guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else { fail("Не створено графічний контекст") }
NSGraphicsContext.current = ctx
let cg = ctx.cgContext
cg.setFillColor(NSColor.white.cgColor); cg.fill(CGRect(x: 0, y: 0, width: W, height: H))
var y = H
for (i, p) in pages.enumerated() {
  let page = doc.page(at: p-1)!, b = page.bounds(for: .mediaBox), s = W / b.width
  NSAttributedString(string: "p.\(p)", attributes: [.font: NSFont.boldSystemFont(ofSize: 18), .foregroundColor: NSColor.red]).draw(at: NSPoint(x: 4, y: y - lab + 4))
  y -= lab
  cg.saveGState()
  cg.clip(to: CGRect(x: 0, y: y - heights[i], width: W, height: heights[i]))
  cg.translateBy(x: 0, y: y - b.height * s)
  cg.scaleBy(x: s, y: s)
  page.draw(with: .mediaBox, to: cg)
  cg.restoreGState()
  y -= heights[i]
}
NSGraphicsContext.restoreGraphicsState()
guard ["jpg", "jpeg"].contains(URL(fileURLWithPath: a[7]).pathExtension.lowercased()) else { fail("Вихід має бути .jpg/.jpeg") }
writeImage(rep, .jpeg, a[7])
