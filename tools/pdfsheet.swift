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

// usage: pdfsheet <pdf> <firstPage 1-based> <lastPage> <cols> <thumbWidth px> <out.jpg>
// Renders a labelled contact sheet of PDF pages for surveying book structure.
let a = CommandLine.arguments
guard a.count == 7 else { fail("Некоректна кількість аргументів; див. коментар використання") }
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])), doc.pageCount > 0 else { fail("PDF не відкрився або порожній") }
let first = positive(a[2], "Перша"), last = positive(a[3], "Остання")
guard first <= last, last <= doc.pageCount else { fail("Діапазон поза PDF або обернений") }
let cols = positive(a[4], "Колонки"), tw = CGFloat(number(a[5], "Ширина"))
let pages = Array(first...last)
let b0 = doc.page(at: first-1)!.bounds(for: .mediaBox)
let th = tw * b0.height / b0.width
let rows = (pages.count + cols - 1) / cols
let lab: CGFloat = 22
checkCanvas(CGFloat(cols) * tw, CGFloat(rows) * (th + lab))
let W = Int(CGFloat(cols) * tw), H = Int(CGFloat(rows) * (th + lab))
guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: W, pixelsHigh: H, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { fail("Не вистачило пам’яті для растра") }
NSGraphicsContext.saveGraphicsState()
guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else { fail("Не створено графічний контекст") }
NSGraphicsContext.current = ctx
let cg = ctx.cgContext
cg.setFillColor(NSColor.white.cgColor); cg.fill(CGRect(x: 0, y: 0, width: W, height: H))
for (i, p) in pages.enumerated() {
  let page = doc.page(at: p-1)!
  let b = page.bounds(for: .mediaBox)
  let r = i / cols, c = i % cols
  let x = CGFloat(c) * tw, yTop = CGFloat(H) - CGFloat(r) * (th + lab)
  let s = min(tw / b.width, th / b.height)
  cg.saveGState()
  cg.translateBy(x: x, y: yTop - lab - b.height * s)
  cg.scaleBy(x: s, y: s)
  page.draw(with: .mediaBox, to: cg)
  cg.restoreGState()
  let str = NSAttributedString(string: "p.\(p)", attributes: [.font: NSFont.boldSystemFont(ofSize: 16), .foregroundColor: NSColor.red])
  str.draw(at: NSPoint(x: x + 4, y: yTop - lab + 3))
}
NSGraphicsContext.restoreGraphicsState()
guard ["jpg", "jpeg"].contains(URL(fileURLWithPath: a[6]).pathExtension.lowercased()) else { fail("Вихід має бути .jpg/.jpeg") }
writeImage(rep, .jpeg, a[6])
