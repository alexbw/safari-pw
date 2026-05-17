// SafariTrustedClick — hit-test an AXUIElement at screen coords and
// invoke its AXPress action.
//
// Why not CGEvent: empirically, CGEventCreateMouseEvent + CGEventPost
// (any tap, any source state, with full HID metadata) DOES produce DOM
// click events with isTrusted=true and DOES trigger link navigation in
// Safari 17/18 — but Safari's download-initiation path has an additional
// gate that silently drops the default action for CGEvent-sourced
// clicks. Real hardware clicks and AXPress invocations both pass this
// gate; CGEvent does not.
//
// AXPress goes through AppKit's NSAccessibility action plumbing, which
// Safari treats as equivalent to a real user-initiated click for the
// purposes of download approval. It's what assistive tech uses to drive
// the UI, so WebKit has to honor it.
//
// Usage:
//   safari-trusted-click X Y
//     Hit-test screen coords (top-left origin, points not pixels).
//   safari-trusted-click --pid PID --name NAME [--role AXLink|AXButton]
//   safari-trusted-click --bundle BUNDLE_ID --name NAME [--role AXLink|AXButton]
//     Walk the target app's AX tree and AXPress the matching named control.
//
// Build:
//   swiftc -O SafariTrustedClick.swift -o safari-trusted-click
//
// Permissions: AXUIElementCopyElementAtPosition + AXUIElementPerformAction
// require the CALLING process to be granted Accessibility access in
// System Settings > Privacy & Security > Accessibility. The first run
// will fail with an AX error until you enable the calling terminal.

import Foundation
import ApplicationServices
import AppKit

func die(_ msg: String, code: Int32 = 2) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(code)
}

let args = Array(CommandLine.arguments.dropFirst())

if args.contains("--help") || args.contains("-h") || args.count < 2 {
    print("""
    usage:
      safari-trusted-click X Y
        Hit-tests an AXUIElement at screen coords (X, Y) and invokes
        AXPress on the nearest ancestor that supports it.

      safari-trusted-click --pid PID --name NAME [--role AXLink|AXButton]
      safari-trusted-click --bundle BUNDLE_ID --name NAME [--role AXLink|AXButton]
        Finds a named pressable control in the app's AX tree and invokes
        AXPress. This avoids browser JS-to-screen coordinate drift.
    """)
    exit(args.count < 2 ? 2 : 0)
}

func supportsPress(_ el: AXUIElement) -> Bool {
    var actionNames: CFArray?
    if AXUIElementCopyActionNames(el, &actionNames) == .success,
       let names = actionNames as? [String] {
        return names.contains("AXPress")
    }
    return false
}

func stringAttr(_ el: AXUIElement, _ attr: String) -> String? {
    var value: CFTypeRef?
    if AXUIElementCopyAttributeValue(el, attr as CFString, &value) == .success {
        return value as? String
    }
    return nil
}

func describe(_ el: AXUIElement) -> String {
    let roleStr = stringAttr(el, kAXRoleAttribute) ?? "?"
    let label = stringAttr(el, kAXTitleAttribute)
        ?? stringAttr(el, kAXDescriptionAttribute)
        ?? stringAttr(el, kAXValueAttribute)
        ?? ""
    return "\(roleStr) \"\(label)\""
}

func press(_ el: AXUIElement, context: String) -> Never {
    let pressErr = AXUIElementPerformAction(el, "AXPress" as CFString)
    if pressErr == .success {
        print("AXPress'd \(describe(el)) \(context)")
        exit(0)
    }
    die("AXPress failed on \(describe(el)): \(pressErr.rawValue)")
}

func normalized(_ s: String) -> String {
    return s.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ").lowercased()
}

func children(_ el: AXUIElement) -> [AXUIElement] {
    var value: CFTypeRef?
    if AXUIElementCopyAttributeValue(el, kAXChildrenAttribute as CFString, &value) == .success,
       let kids = value as? [AXUIElement] {
        return kids
    }
    return []
}

func pressNamed(pid: pid_t, name: String, role wantedRole: String?) -> Never {
    let app = AXUIElementCreateApplication(pid)
    let needle = normalized(name)
    if needle.isEmpty {
        die("--name must not be empty")
    }

    var queue: [AXUIElement] = [app]
    var bestContains: AXUIElement?
    var visited = 0
    let maxVisited = 12000

    while !queue.isEmpty && visited < maxVisited {
        let el = queue.removeFirst()
        visited += 1

        let role = stringAttr(el, kAXRoleAttribute) ?? ""
        let roleOK = wantedRole == nil || role == wantedRole
        if roleOK && supportsPress(el) {
            let labels = [
                stringAttr(el, kAXTitleAttribute),
                stringAttr(el, kAXDescriptionAttribute),
                stringAttr(el, kAXValueAttribute),
                stringAttr(el, kAXHelpAttribute)
            ].compactMap { $0 }.map(normalized)

            if labels.contains(needle) {
                press(el, context: "matched name \"\(name)\" after \(visited) AX nodes")
            }
            if bestContains == nil && labels.contains(where: { $0.contains(needle) || needle.contains($0) }) {
                bestContains = el
            }
        }

        queue.append(contentsOf: children(el))
    }

    if let el = bestContains {
        press(el, context: "matched name containing \"\(name)\" after \(visited) AX nodes")
    }
    die("no AXPress-supporting element named \"\(name)\" found after \(visited) AX nodes")
}

if args[0] == "--pid" || args[0] == "--bundle" {
    guard args.count >= 4, args[2] == "--name" else {
        die("usage: safari-trusted-click (--pid PID|--bundle BUNDLE_ID) --name NAME [--role AXRole]")
    }
    let pid: pid_t
    if args[0] == "--pid" {
        guard let parsed = Int32(args[1]) else {
            die("--pid must be an integer")
        }
        pid = parsed
    } else {
        let matches = NSRunningApplication.runningApplications(withBundleIdentifier: args[1])
            .filter { !$0.isTerminated }
        guard let app = matches.first else {
            die("no running application with bundle id \(args[1])")
        }
        pid = app.processIdentifier
    }
    var role: String? = nil
    if let roleIdx = args.firstIndex(of: "--role"), roleIdx + 1 < args.count {
        role = args[roleIdx + 1]
    }
    pressNamed(pid: pid, name: args[3], role: role)
}

guard let x = Double(args[0]), let y = Double(args[1]) else {
    die("X and Y must be numbers, got \(args[0]) \(args[1])")
}

let sysWideAX = AXUIElementCreateSystemWide()
var hit: AXUIElement?
let hitErr = AXUIElementCopyElementAtPosition(sysWideAX, Float(x), Float(y), &hit)
if hitErr != .success {
    die("AX hit-test at (\(x),\(y)) failed: \(hitErr.rawValue) — check Accessibility permission for the calling process")
}
guard let target = hit else {
    die("AX hit-test returned no element at (\(x),\(y))")
}

// Walk up the AX tree to find the nearest ancestor that exposes AXPress.
// The hit element is often a static text inside a link/button; AXPress
// lives on the interactive ancestor, not the text node.
var current: AXUIElement? = target
var depth = 0
while let el = current, depth < 12 {
    if supportsPress(el) {
        press(el, context: "at (\(x),\(y)) depth=\(depth)")
    }
    var parent: CFTypeRef?
    AXUIElementCopyAttributeValue(el, kAXParentAttribute as CFString, &parent)
    if parent == nil { break }
    current = (parent as! AXUIElement)
    depth += 1
}
die("no AXPress-supporting element within \(depth) ancestors of (\(x),\(y))")
