import AppKit
import SwiftUI

@main
struct VocifyHostApp: App {
    @StateObject private var host = HostController()

    init() {
        NSApplication.shared.setActivationPolicy(.regular)
    }

    var body: some Scene {
        WindowGroup {
            WebShellView(host: host)
                .frame(minWidth: 720, minHeight: 600)
        }
        .defaultSize(width: 900, height: 720)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .appInfo) {
                Button("Acerca de Vocify") {
                    NSApplication.shared.orderFrontStandardAboutPanel(nil)
                }
            }
            CommandMenu("Nota") {
                Button("Nueva nota") {
                    host.emitCommand("show")
                }
                .keyboardShortcut("n", modifiers: .command)

                Button("Grabar/Parar") {
                    host.toggleListenStop()
                }
                .keyboardShortcut("r", modifiers: .command)
            }
        }
    }
}
