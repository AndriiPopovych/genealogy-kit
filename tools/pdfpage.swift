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

// usage: pdfpage <pdf> <page 1-based> <out.png> [scale]
let a = CommandLine.arguments
guard a.count == 3 || a.count == 4 || a.count == 5 else { fail("Некоректна кількість аргументів; див. коментар використання") }
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])), doc.pageCount > 0 else { fail("PDF не відкрився або порожній") }
if a[2] == "count" { print(doc.pageCount); exit(0) }
guard a.count >= 4 else { fail("Потрібен вихідний PNG") }
let pageNumber = positive(a[2], "Сторінка")
guard pageNumber <= doc.pageCount, let page = doc.page(at: pageNumber - 1) else { fail("Сторінка поза PDF") }
let s = a.count > 4 ? CGFloat(number(a[4], "Масштаб")) : 2.0
let b = page.bounds(for: .mediaBox)
checkCanvas(b.width*s, b.height*s)
guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(b.width*s), pixelsHigh: Int(b.height*s), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { fail("Не вистачило пам’яті для растра") }
NSGraphicsContext.saveGraphicsState()
guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else { fail("Не створено графічний контекст") }
NSGraphicsContext.current = ctx
ctx.cgContext.setFillColor(NSColor.white.cgColor); ctx.cgContext.fill(CGRect(x:0,y:0,width:b.width*s,height:b.height*s))
ctx.cgContext.scaleBy(x: s, y: s)
page.draw(with: .mediaBox, to: ctx.cgContext)
NSGraphicsContext.restoreGraphicsState()
guard a[3].lowercased().hasSuffix(".png") else { fail("Вихід має бути .png") }
writeImage(rep, .png, a[3])
