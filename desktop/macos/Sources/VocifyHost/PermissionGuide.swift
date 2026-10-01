import AppKit
import CoreGraphics

private let settingsOwners: Set<String> = ["System Settings", "System Preferences"]
private let guideWidth: CGFloat = 340
private let guideGap: CGFloat = 28

private enum GuideCopy {
    static var isSpanish: Bool { Locale.preferredLanguages.first?.hasPrefix("es") ?? false }
    static var title: String { isSpanish ? "Arrastra Vocify a Ajustes" : "Drag Vocify into Settings" }
    static var hint: String {
        isSpanish
            ? "Suéltalo en la lista de Grabación de pantalla y audio del sistema, y activa el interruptor."
            : "Drop it in the Screen & System Audio Recording list, then switch it on."
    }
    static var close: String { isSpanish ? "Cerrar" : "Close" }
}

/// Dims everything except the System Settings window, so the eye lands on the list we want Vocify dropped into.
private final class DimView: NSView {
    var hole: NSRect? { didSet { needsDisplay = true } }

    override func draw(_ dirtyRect: NSRect) {
        let path = NSBezierPath(rect: bounds)
        if let hole {
            path.append(NSBezierPath(roundedRect: hole, xRadius: 14, yRadius: 14))
            path.windingRule = .evenOdd
        }
        NSColor.black.withAlphaComponent(0.62).setFill()
        path.fill()
    }
}

/// A chip that drags the Vocify.app bundle itself, which is what the "+" file picker in Settings would add.
private final class AppChipView: NSView, NSDraggingSource {
    private let appURL = Bundle.main.bundleURL
    private let icon = NSWorkspace.shared.icon(forFile: Bundle.main.bundlePath)

    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        let card = NSBezierPath(roundedRect: bounds.insetBy(dx: 1, dy: 1), xRadius: 14, yRadius: 14)
        NSColor.white.setFill()
        card.fill()
        icon.draw(in: NSRect(x: 16, y: 13, width: 34, height: 34))
        let name = (Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String) ?? "Vocify"
        (name as NSString).draw(
            at: NSPoint(x: 62, y: 19),
            withAttributes: [.font: NSFont.systemFont(ofSize: 17, weight: .medium), .foregroundColor: NSColor.black]
        )
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: .openHand)
    }

    override func mouseDragged(with event: NSEvent) {
        let item = NSDraggingItem(pasteboardWriter: appURL as NSURL)
        item.setDraggingFrame(NSRect(x: 0, y: 0, width: 64, height: 64), contents: icon)
        beginDraggingSession(with: [item], event: event, source: self)
    }

    func draggingSession(_ session: NSDraggingSession, sourceOperationMaskFor context: NSDraggingContext) -> NSDragOperation {
        .copy
    }
}

private final class GuideContentView: NSView {
    var onClose: (() -> Void)?

    init(frame: NSRect, chip: AppChipView) {
        super.init(frame: frame)

        let title = NSTextField(wrappingLabelWithString: GuideCopy.title)
        title.font = {
            let base = NSFont.systemFont(ofSize: 34, weight: .regular)
            return base.fontDescriptor.withDesign(.serif).flatMap { NSFont(descriptor: $0, size: 34) } ?? base
        }()
        title.textColor = .white
        title.frame = NSRect(x: 0, y: frame.height - 92, width: frame.width, height: 92)
        title.alignment = .left

        chip.frame = NSRect(x: 0, y: frame.height - 92 - 18 - 60, width: frame.width, height: 60)

        let hint = NSTextField(wrappingLabelWithString: GuideCopy.hint)
        hint.font = .systemFont(ofSize: 13)
        hint.textColor = NSColor.white.withAlphaComponent(0.72)
        hint.frame = NSRect(x: 0, y: 34, width: frame.width, height: 54)

        let close = NSButton(title: GuideCopy.close, target: self, action: #selector(closeTapped))
        close.isBordered = false
        close.contentTintColor = NSColor.white.withAlphaComponent(0.72)
        close.font = .systemFont(ofSize: 13, weight: .medium)
        close.sizeToFit()
        close.frame.origin = NSPoint(x: 0, y: 0)

        [title, chip, hint, close].forEach(addSubview)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc private func closeTapped() { onClose?() }
}

final class PermissionGuideController {
    private var dimWindows: [(window: NSWindow, view: DimView)] = []
    private var guidePanel: NSPanel?
    private var timer: Timer?
    private var settingsMissingTicks = 0

    var isShowing: Bool { guidePanel != nil }

    func show() {
        guard !isShowing else { return }
        settingsMissingTicks = 0

        for screen in NSScreen.screens {
            let view = DimView(frame: NSRect(origin: .zero, size: screen.frame.size))
            let window = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
            window.level = .floating
            window.isOpaque = false
            window.backgroundColor = .clear
            window.hasShadow = false
            window.ignoresMouseEvents = true
            window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
            window.contentView = view
            window.orderFrontRegardless()
            dimWindows.append((window, view))
        }

        let chip = AppChipView()
        let height: CGFloat = 92 + 18 + 60 + 14 + 54 + 34
        let content = GuideContentView(frame: NSRect(x: 0, y: 0, width: guideWidth, height: height), chip: chip)
        content.onClose = { [weak self] in self?.dismiss() }
        let panel = NSPanel(
            contentRect: content.frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.hidesOnDeactivate = false
        panel.isFloatingPanel = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentView = content
        panel.orderFrontRegardless()
        guidePanel = panel

        track()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.track() }
    }

    func dismiss() {
        timer?.invalidate()
        timer = nil
        dimWindows.forEach { $0.window.orderOut(nil) }
        dimWindows.removeAll()
        guidePanel?.orderOut(nil)
        guidePanel = nil
    }

    private func track() {
        if CGPreflightScreenCaptureAccess() {
            dismiss()
            return
        }
        guard let settings = Self.settingsFrame() else {
            // Settings hasn't drawn yet on launch; once it was seen and is gone, the user closed it.
            settingsMissingTicks += 1
            if settingsMissingTicks > 40 { dismiss() }
            return
        }
        settingsMissingTicks = 0
        for (window, view) in dimWindows {
            view.hole = settings.intersection(window.frame).offsetBy(dx: -window.frame.minX, dy: -window.frame.minY)
        }
        positionGuide(beside: settings)
    }

    private func positionGuide(beside settings: NSRect) {
        guard let panel = guidePanel else { return }
        let screen = NSScreen.screens.first { $0.frame.intersects(settings) } ?? NSScreen.main
        let visible = screen?.visibleFrame ?? settings
        let size = panel.frame.size
        let rightRoom = visible.maxX - settings.maxX
        let x = rightRoom >= size.width + guideGap * 2
            ? settings.maxX + guideGap
            : max(visible.minX + guideGap, settings.minX - size.width - guideGap)
        let y = min(max(visible.minY + guideGap, settings.maxY - size.height - guideGap), visible.maxY - size.height - guideGap)
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    /// Frontmost System Settings window in Cocoa coordinates (CG reports top-left origin).
    private static func settingsFrame() -> NSRect? {
        guard let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]],
              let primaryHeight = NSScreen.screens.first?.frame.height
        else { return nil }
        for entry in info {
            guard let owner = entry[kCGWindowOwnerName as String] as? String, settingsOwners.contains(owner),
                  (entry[kCGWindowLayer as String] as? Int) == 0,
                  let bounds = entry[kCGWindowBounds as String] as? [String: CGFloat],
                  let x = bounds["X"], let y = bounds["Y"], let w = bounds["Width"], let h = bounds["Height"],
                  w > 300, h > 300
            else { continue }
            return NSRect(x: x, y: primaryHeight - y - h, width: w, height: h)
        }
        return nil
    }
}
