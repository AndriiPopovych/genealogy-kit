import PDFKit
// Використання: pdftext <pdf>; текстовий шар, не OCR.
func fail(_ message: String) -> Never { FileHandle.standardError.write(Data(("Помилка: " + message + "\n").utf8)); exit(1) }
guard CommandLine.arguments.count == 2 else { fail("Використання: pdftext <pdf>") }
guard let doc = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])), doc.pageCount > 0 else { fail("PDF не відкрився або порожній") }
for i in 0..<doc.pageCount { print("Сторінка \(i+1)"); print(doc.page(at: i)?.string ?? "") }
