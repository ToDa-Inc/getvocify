import AppKit
import Foundation

let args = CommandLine.arguments
guard args.count == 3 else {
    fputs("usage: draw-app-icon.swift logo.png out.png\n", stderr)
    exit(1)
}
guard let mark = NSImage(contentsOfFile: args[1]) else {
    fputs("missing logo\n", stderr)
    exit(1)
}

let canvasSize: CGFloat = 1024
let tileSize: CGFloat = 824
let cornerRadius: CGFloat = 185
let markSize: CGFloat = 560

guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: Int(canvasSize),
    pixelsHigh: Int(canvasSize),
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
) else {
    fputs("bitmap failed\n", stderr)
    exit(1)
}

rep.size = NSSize(width: canvasSize, height: canvasSize)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.clear.setFill()
NSRect(x: 0, y: 0, width: canvasSize, height: canvasSize).fill()

let tileOrigin = (canvasSize - tileSize) / 2
let tileRect = NSRect(x: tileOrigin, y: tileOrigin, width: tileSize, height: tileSize)

let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.14)
shadow.shadowOffset = NSSize(width: 0, height: -6)
shadow.shadowBlurRadius = 28
shadow.set()

let tilePath = NSBezierPath(roundedRect: tileRect, xRadius: cornerRadius, yRadius: cornerRadius)
NSColor(srgbRed: 0xf7 / 255, green: 0xf4 / 255, blue: 0xee / 255, alpha: 1).setFill()
tilePath.fill()

NSShadow().set()

let markOrigin = (canvasSize - markSize) / 2
mark.draw(in: NSRect(x: markOrigin, y: markOrigin, width: markSize, height: markSize))

NSGraphicsContext.restoreGraphicsState()

guard let png = rep.representation(using: .png, properties: [:]) else {
    fputs("png export failed\n", stderr)
    exit(1)
}
try png.write(to: URL(fileURLWithPath: args[2]))
