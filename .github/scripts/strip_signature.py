"""Enlève la signature numérique (Authenticode) d'un .exe.

ApexRadio.exe est une copie de pythonw.exe, qui est signé par la Python Software Foundation.
Quand rcedit change l'icône et le nom, la signature devient invalide (elle pointe après la fin
du fichier) et le Microsoft Store refuse le paquet : « Erreur de signature 0x800700C1 ».
On enlève donc la signature avant rcedit ; le Store signe lui-même le paquet MSIX.

Usage : python strip_signature.py fichier.exe [--check]
  --check : ne modifie rien, échoue si le fichier a une signature abîmée.
"""
import os
import struct
import sys


def sec_dir(data: bytes) -> int:
    """Position, dans le fichier, de l'entrée « Certificate Table » des en-têtes PE."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("pas un fichier PE")
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (96 if magic == 0x10B else 112)   # PE32 ou PE32+
    return dirs + 4 * 8                             # 5e répertoire (index 4)


def main():
    path = sys.argv[1]
    check = "--check" in sys.argv
    data = bytearray(open(path, "rb").read())
    pos = sec_dir(data)
    off, size = struct.unpack_from("<II", data, pos)
    if off == 0 and size == 0:
        print(f"{path} : pas de signature")
        return
    broken = off + size > len(data)
    if check:
        if broken:
            sys.exit(f"{path} : signature abîmée (elle dépasse la fin du fichier)")
        print(f"{path} : signature présente et entière")
        return
    struct.pack_into("<II", data, pos, 0, 0)
    if not broken and off + size == len(data):
        del data[off:]                              # la signature était à la fin : on la coupe
    open(path, "wb").write(data)
    print(f"{path} : signature enlevée ({size} octets)")


if __name__ == "__main__":
    main()
