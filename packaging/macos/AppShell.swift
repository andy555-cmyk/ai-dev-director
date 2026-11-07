// AI Dev Director · native macOS shell (0.4.1, 0.4.2 앱 열어 보기 창)
// The app is its own window now: it starts the local engine (Resources/start.command) as a child, waits for
// 127.0.0.1:8081/health and shows the HUD in a WKWebView. No browser tab. Quitting the app stops the engine;
// records and worktrees stay and interrupted missions resume on the next start (resume_on_start).
import AppKit
import WebKit

let engineURL = URL(string: "http://127.0.0.1:8081/")!
let healthURL = URL(string: "http://127.0.0.1:8081/health")!
let appData = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/AI Dev Director")

func isLocal(_ url: URL?) -> Bool {
    guard let url = url else { return false }
    if url.scheme == "about" || url.scheme == "blob" || url.scheme == "data" { return true }
    // The engine (8081) and the 「앱 열어 보기」 previews (other local ports) stay inside the app.
    return ["127.0.0.1", "localhost"].contains(url.host ?? "")
}

func checkHealth(_ done: @escaping (Bool) -> Void) {
    var req = URLRequest(url: healthURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 1)
    req.httpMethod = "GET"
    URLSession.shared.dataTask(with: req) { data, _, _ in
        let ok = data.flatMap { String(data: $0, encoding: .utf8) }?.contains("ai-dev-director-macos") ?? false
        DispatchQueue.main.async { done(ok) }
    }.resume()
}

final class WebWindow: NSObject, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    let window: NSWindow
    let web: WKWebView
    var onClose: ((WebWindow) -> Void)?
    var titleWatch: NSKeyValueObservation?

    init(configuration: WKWebViewConfiguration, frame: NSRect, title: String) {
        window = NSWindow(contentRect: frame, styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        web = WKWebView(frame: .zero, configuration: configuration)
        super.init()
        window.title = title
        window.minSize = NSSize(width: 960, height: 640)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.backgroundColor = NSColor(calibratedRed: 0.03, green: 0.05, blue: 0.09, alpha: 1)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsMagnification = true
        web.setValue(false, forKey: "drawsBackground")
        window.contentView = web
        titleWatch = web.observe(\.title, options: [.new]) { [weak self] w, _ in
            if let t = w.title, !t.isEmpty { self?.window.title = t }
        }
    }

    func windowWillClose(_ notification: Notification) { onClose?(self) }

    // Links that leave the local engine open in the default browser; local pages stay in the app.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.shouldPerformDownload { return decisionHandler(.download) }
        if let url = action.request.url, !isLocal(url) {
            NSWorkspace.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disposition = (response.response as? HTTPURLResponse)?
            .value(forHTTPHeaderField: "Content-Disposition")?.lowercased() ?? ""
        decisionHandler(!response.canShowMIMEType || disposition.hasPrefix("attachment") ? .download : .allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.url : nil) }
    }

    // window.open / target=_blank: local pages get their own app window, outside pages go to the browser.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard isLocal(action.request.url) else {
            if let url = action.request.url { NSWorkspace.shared.open(url) }
            return nil
        }
        return AppDelegate.shared.openChild(configuration: configuration).web
    }

    func webViewDidClose(_ webView: WKWebView) { window.close() }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "확인")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "확인")
        alert.addButton(withTitle: "취소")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let alert = NSAlert()
        alert.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
        field.stringValue = defaultText ?? ""
        alert.accessoryView = field
        alert.addButton(withTitle: "확인")
        alert.addButton(withTitle: "취소")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    // The engine stopped (시스템 중지 or a crash): show the waiting screen instead of a dead page.
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if self === AppDelegate.shared.main { AppDelegate.shared.engineLost() }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    static let shared = AppDelegate()
    let config = WKWebViewConfiguration()
    var main: WebWindow!
    var children: [WebWindow] = []
    var engine: Process?
    var waitTimer: Timer?
    var waitStarted = Date()
    var quitting = false
    let status = NSTextField(labelWithString: "")
    let detail = NSTextField(labelWithString: "")
    let spinner = NSProgressIndicator()
    var placeholder: NSView!

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        config.websiteDataStore = .default()
        config.preferences.javaScriptCanOpenWindowsAutomatically = true
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let size = NSSize(width: min(1440, screen.width - 40), height: min(920, screen.height - 40))
        main = WebWindow(configuration: config, frame: NSRect(origin: .zero, size: size), title: "AI Dev Director")
        main.window.setFrameAutosaveName("AIDevDirectorMain")
        if main.window.frame.size.width < 960 { main.window.setContentSize(size) }
        if !main.window.setFrameUsingName("AIDevDirectorMain") { main.window.center() }
        buildPlaceholder()
        main.window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startOrAttach()
    }

    func buildPlaceholder() {
        let view = NSView()
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor(calibratedRed: 0.03, green: 0.05, blue: 0.09, alpha: 1).cgColor
        status.font = .systemFont(ofSize: 22, weight: .semibold)
        status.textColor = .white
        detail.font = .systemFont(ofSize: 15)
        detail.textColor = NSColor(white: 0.75, alpha: 1)
        detail.alignment = .center
        detail.maximumNumberOfLines = 3
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.appearance = NSAppearance(named: .darkAqua)
        let stack = NSStackView(views: [spinner, status, detail])
        stack.orientation = .vertical
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
                                     stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
                                     detail.widthAnchor.constraint(lessThanOrEqualToConstant: 560)])
        placeholder = view
    }

    func showWaiting(_ title: String, _ sub: String, spinning: Bool = true) {
        status.stringValue = title
        detail.stringValue = sub
        spinning ? spinner.startAnimation(nil) : spinner.stopAnimation(nil)
        spinner.isHidden = !spinning
        main.window.contentView = placeholder
    }

    func startOrAttach() {
        showWaiting("AI Dev Director 켜는 중", "처음 켤 때는 필요한 구성 요소를 받느라 1~2분 걸립니다")
        checkHealth { ok in
            if ok { self.showEngine() } else { self.launchEngine() }
        }
    }

    func launchEngine() {
        if engine?.isRunning == true { return waitForEngine() }
        guard let start = Bundle.main.url(forResource: "start", withExtension: "command") else {
            return showFailure("앱 안의 실행 파일을 찾지 못했습니다")
        }
        try? FileManager.default.createDirectory(at: appData, withIntermediateDirectories: true)
        let logURL = appData.appendingPathComponent("launcher.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logURL)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [start.path, "--background"]
        var env = ProcessInfo.processInfo.environment
        env["BROWSER"] = "true"                 // mac_bootstrap must not open a browser tab: this window is the screen
        env["AI_DEV_DIRECTOR_APP"] = "1"
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = log ?? FileHandle.nullDevice
        p.standardError = log ?? FileHandle.nullDevice
        p.terminationHandler = { proc in
            DispatchQueue.main.async {
                guard !self.quitting else { return }
                checkHealth { ok in
                    if !ok && self.main.window.contentView === self.placeholder {
                        self.showFailure("엔진이 켜지지 않았습니다 (종료 코드 \(proc.terminationStatus))")
                    }
                }
            }
        }
        do { try p.run() } catch { return showFailure("엔진을 실행하지 못했습니다: \(error.localizedDescription)") }
        engine = p
        waitForEngine()
    }

    func waitForEngine() {
        waitStarted = Date()
        waitTimer?.invalidate()
        waitTimer = Timer.scheduledTimer(withTimeInterval: 0.7, repeats: true) { timer in
            checkHealth { ok in
                if ok { timer.invalidate(); self.showEngine() }
                else if Date().timeIntervalSince(self.waitStarted) > 240 {
                    timer.invalidate()
                    self.showFailure("4분이 지나도 엔진이 응답하지 않습니다")
                }
            }
        }
    }

    func showEngine() {
        main.window.contentView = main.web
        spinner.stopAnimation(nil)
        if main.web.url == nil || !isLocal(main.web.url) { main.web.load(URLRequest(url: engineURL)) }
        else { main.web.reload() }
    }

    func engineLost() {
        guard !quitting else { return }
        checkHealth { ok in
            if ok { return }
            self.showWaiting("엔진이 멈춰 있습니다", "다시 켜려면 아래 메뉴의 「엔진 다시 켜기」(⌘⇧R)를 누르세요", spinning: false)
        }
    }

    func showFailure(_ message: String) {
        showWaiting("켜지 못했습니다", message + "\n기록: ~/Library/Application Support/AI Dev Director/launcher.log", spinning: false)
    }

    func openChild(configuration: WKWebViewConfiguration) -> WebWindow {
        let frame = NSRect(x: 0, y: 0, width: 1100, height: 760)
        let child = WebWindow(configuration: configuration, frame: frame, title: "AI Dev Director")
        child.onClose = { [weak self] w in self?.children.removeAll { $0 === w } }
        children.append(child)
        child.window.cascadeTopLeft(from: main.window.frame.origin)
        child.window.makeKeyAndOrderFront(nil)
        return child
    }

    @objc func restartEngine(_ sender: Any?) {
        if main.window.contentView === main.web, engine?.isRunning != true {
            checkHealth { ok in if ok { self.main.web.reload() } else { self.startOrAttach() } }
        } else { startOrAttach() }
    }

    @objc func reloadPage(_ sender: Any?) {
        (NSApp.keyWindow?.contentView as? WKWebView ?? main.web).reload()
    }

    @objc func zoomIn(_ sender: Any?) { zoom(by: 0.1) }
    @objc func zoomOut(_ sender: Any?) { zoom(by: -0.1) }
    @objc func zoomReset(_ sender: Any?) { (NSApp.keyWindow?.contentView as? WKWebView ?? main.web).pageZoom = 1 }
    func zoom(by delta: CGFloat) {
        let w = NSApp.keyWindow?.contentView as? WKWebView ?? main.web
        w.pageZoom = max(0.6, min(2.0, w.pageZoom + delta))
    }

    @objc func openLog(_ sender: Any?) {
        NSWorkspace.shared.open(appData.appendingPathComponent("launcher.log"))
    }

    // Closing the window keeps the app (and any running build) alive; the Dock icon brings it back.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { main.window.makeKeyAndOrderFront(nil) }
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "AI Dev Director를 끌까요"
        alert.informativeText = "진행 중인 작업은 멈췄다가 다음에 켤 때 이어서 진행합니다"
        alert.addButton(withTitle: "끄기")
        alert.addButton(withTitle: "취소")
        if alert.runModal() != .alertFirstButtonReturn { return .terminateCancel }
        quitting = true
        showWaiting("끄는 중", "기록을 저장하고 엔진을 멈추고 있습니다")
        DispatchQueue.global().async {
            stopEngine()
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }

    func buildMenu() {
        let bar = NSMenu()
        func add(_ title: String, _ items: [NSMenuItem]) {
            let top = NSMenuItem()
            let menu = NSMenu(title: title)
            items.forEach(menu.addItem)
            top.submenu = menu
            bar.addItem(top)
        }
        func item(_ t: String, _ a: Selector?, _ k: String, _ mods: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let i = NSMenuItem(title: t, action: a, keyEquivalent: k)
            i.keyEquivalentModifierMask = mods
            return i
        }
        add("AI Dev Director", [
            item("AI Dev Director 정보", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("AI Dev Director 가리기", #selector(NSApplication.hide(_:)), "h"),
            item("기타 가리기", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            .separator(),
            item("AI Dev Director 끝내기", #selector(NSApplication.terminate(_:)), "q"),
        ])
        add("편집", [
            item("실행 취소", Selector(("undo:")), "z"),
            item("실행 복귀", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("오려두기", #selector(NSText.cut(_:)), "x"),
            item("복사하기", #selector(NSText.copy(_:)), "c"),
            item("붙여넣기", #selector(NSText.paste(_:)), "v"),
            item("전체 선택", #selector(NSText.selectAll(_:)), "a"),
        ])
        add("보기", [
            item("새로 고침", #selector(reloadPage(_:)), "r"),
            item("엔진 다시 켜기", #selector(restartEngine(_:)), "r", [.command, .shift]),
            .separator(),
            item("크게", #selector(zoomIn(_:)), "="),
            item("작게", #selector(zoomOut(_:)), "-"),
            item("원래 크기", #selector(zoomReset(_:)), "0"),
            .separator(),
            item("전체 화면", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
            .separator(),
            item("실행 기록 열기", #selector(openLog(_:)), ""),
        ])
        add("윈도우", [
            item("최소화", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("닫기", #selector(NSWindow.performClose(_:)), "w"),
        ])
        bar.items.forEach { m in m.submenu?.items.forEach { if $0.target == nil && $0.action != nil &&
            self.responds(to: $0.action!) { $0.target = self } } }
        NSApp.mainMenu = bar
    }
}

// Same order as the HUD 「시스템 중지」 path: mac_bootstrap forwards SIGINT to the companion server group.
func healthSync() -> Bool {
    let sem = DispatchSemaphore(value: 0)
    var ok = false
    var req = URLRequest(url: healthURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 1)
    req.httpMethod = "GET"
    URLSession.shared.dataTask(with: req) { data, _, _ in
        ok = data.flatMap { String(data: $0, encoding: .utf8) }?.contains("ai-dev-director-macos") ?? false
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + 2)
    return ok
}

func stopEngine() {
    func run(_ args: [String]) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        p.arguments = args
        try? p.run()
        p.waitUntilExit()
    }
    run(["-INT", "-f", "Contents/Resources/mac_bootstrap.py"])
    for _ in 0..<20 {
        if !healthSync() { return }
        Thread.sleep(forTimeInterval: 0.5)
    }
    run(["-INT", "-f", "companion_server.py"])
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
app.delegate = AppDelegate.shared
app.run()
