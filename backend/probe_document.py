"""A labelled synthetic PDF for live integration checks (standard library only)."""
def probe_pdf():
    # A deliberately labelled one-page integration-test document, never business evidence.
    content = b'BT /F1 16 Tf 40 150 Td (TRUESTATE DEPLOYMENT CHECK) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream']
    document = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(document)); document += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(document)
    document += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:
        document += f'{offset:010d} 00000 n \n'.encode()
    document += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(document)
