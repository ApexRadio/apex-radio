"""Test de la fenêtre intégrée sur la machine de build : ouvre la fenêtre, vérifie qu'elle charge, la ferme."""
import os
import sys
import threading

sys.path.insert(0, os.getcwd())
import webview  # noqa: E402

import desktop  # noqa: E402

threading.Timer(60, lambda: (print("FENETRE : délai dépassé"), os._exit(2))).start()
w = webview.create_window("Apex Radio", html="<body style='background:#06070B;color:#fff'>Apex Radio OK</body>")


def loaded():
    h = None
    try:
        h = int(w.native.Handle.ToInt64())
        desktop._set_icon(h)
    except Exception as e:
        print("icone :", e)
    print("FENETRE OK, hwnd", h, "texte :", w.evaluate_js("document.body.innerText"))
    sys.stdout.flush()
    os._exit(0)


w.events.loaded += loaded
webview.start(gui="edgechromium")
print("FENETRE : boucle terminée sans chargement")
os._exit(3)
