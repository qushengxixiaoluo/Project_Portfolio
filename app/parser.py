"""文件文本提取与分块。"""
from pathlib import Path

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".log", ".rst",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".bat", ".ps1", ".sql", ".r",
    ".html", ".css", ".vue", ".swift", ".kt", ".scala", ".lua", ".pl",
    ".xml", ".svg", ".env", ".gitignore", ".dockerfile", ".makefile",
}

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
PREVIEW_LIMIT = 4000


class UnsupportedFile(Exception):
    pass


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(path: Path) -> str:
    """按扩展名提取文本，不支持的类型抛 UnsupportedFile。"""
    ext = path.suffix.lower()
    name = path.name.lower()

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)

    if ext == ".docx":
        import docx
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)

    if ext in TEXT_EXTS or ext == "" or name in ("dockerfile", "makefile", "license"):
        return read_text_file(path)

    raise UnsupportedFile(f"暂不支持的文件类型：{path.name}")


def chunk_text(text: str) -> list[str]:
    """按段落聚合到约 CHUNK_SIZE 字一块，块间保留 CHUNK_OVERLAP 重叠。"""
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        # 单段超长则硬切
        while len(para) > CHUNK_SIZE:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(para[:CHUNK_SIZE])
            para = para[CHUNK_SIZE - CHUNK_OVERLAP:]
        if len(buf) + len(para) + 2 > CHUNK_SIZE and buf:
            chunks.append(buf)
            tail = buf[-CHUNK_OVERLAP:]
            buf = (tail + "\n\n" + para) if tail else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


def preview_of(text: str) -> str:
    return text[:PREVIEW_LIMIT]
