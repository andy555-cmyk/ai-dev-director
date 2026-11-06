"""Native Windows folder dialog for the 8081 console. A browser never reveals a folder's absolute path, so the local
companion server runs this helper and reads the choice from stdout: one JSON line {"path": "..."} ("" = cancelled)."""
import json
import sys


def main() -> int:
    if sys.platform == "darwin":
        import subprocess
        # No user-controlled strings are interpolated into AppleScript.
        result = subprocess.run(["/usr/bin/osascript", "-e",
            'try\nreturn POSIX path of (choose folder with prompt "AI DEV DIRECTOR - 프로젝트 폴더 선택")\non error number -128\nreturn ""\nend try'],
            capture_output=True, text=True)
        if result.returncode:
            return result.returncode
        sys.stdout.buffer.write(json.dumps({"path": result.stdout.strip()}).encode("ascii"))
        return 0
    import tkinter
    from tkinter import filedialog
    initial = sys.argv[1] if len(sys.argv) > 1 else ""
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)          # the dialog must not open behind the browser
    root.update()
    chosen = filedialog.askdirectory(parent=root, initialdir=initial or None, mustexist=True,
                                     title="AI DEV DIRECTOR - 작업할 폴더 선택")
    root.destroy()
    sys.stdout.buffer.write(json.dumps({"path": chosen or ""}).encode("ascii"))   # ensure_ascii: safe on any codepage
    return 0


if __name__ == "__main__":
    sys.exit(main())
