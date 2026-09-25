import AppKit
import Foundation

let args = CommandLine.arguments
guard args.count == 3 else {
    fputs("usage: draw-dmg-background logo.png out.png\n", stderr)
    exit(1)
}
let logo = NSImage(contentsOfFile: args[1])
let size = NSSize(width: 540, height: 380)
let image = NSImage(size: size)
image.lockFocus()
NSColor(calibratedRed: 0.97, green: 0.956, blue: 0.933, alpha: 1).setFill()
NSBezierPath(rect: NSRect(origin: .zero, size: size)).fill()
let title = "Arrastra Vocify a Aplicaciones" as NSString
let attrs: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 18, weight: .medium),
    .foregroundColor: NSColor(calibratedWhite: 0.25, alpha: 1),
]
title.draw(at: NSPoint(x: 150, y: 300), withAttributes: attrs)
logo?.draw(in: NSRect(x: 24, y: 300, width: 48, height: 48))
image.unlockFocus()
guard let tiff = image.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else {
    fputs("no png\n", stderr)
    exit(1)
}
try png.write(to: URL(fileURLWithPath: args[2]))
