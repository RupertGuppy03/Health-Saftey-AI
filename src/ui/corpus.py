"""The list of source documents shown in the interface sidebar.

Reads the PDFs straight off disk under data/raw/. It deliberately does not use
src/embeddings/corpus.py, which answers a similar question but imports the
vector store client, and the interface must not pull ChromaDB in.

Nothing here opens a PDF. Only names and paths are handled, so listing the
corpus costs nothing even though the files themselves are large.
"""

from pathlib import Path

from src.config.settings import DATA_RAW_DIR

# Every filename ends in this WorkSafe suffix ("good practice guidelines"). It
# is on all 25 of them, so it carries no information and only makes the titles
# harder to scan.
GUIDE_SUFFIX = "gpg"

# Words that stay lowercase inside a title, unless they start it.
SMALL_WORDS = {
    "a", "an", "and", "at", "by", "for", "in", "near", "of", "on", "or",
    "the", "to", "while", "with", "your",
}

# Words the general rules get wrong. Kept deliberately short -- it is for
# acronyms the corpus actually uses, not a place to hand-write titles.
ACRONYMS = {
    "pcbus": "PCBUs",
    "nz": "NZ",
}


def document_title(filename):
    """A readable title from a stored PDF filename.

    The filenames are inconsistent about case ("working-on-roofs-GPG.pdf",
    "scaffolding-in-New-Zealand-gpg.pdf", "PCBUs-Working-Together-GPG.pdf"), so
    a plain .title() mangles them. A word that is already capitalised past its
    first letter is left exactly as it is, which keeps acronyms intact.
    """

    stem = Path(filename).stem

    words = [word for word in stem.split("-") if word]

    if words and words[-1].lower() == GUIDE_SUFFIX:
        words.pop()

    titled = []

    for position, word in enumerate(words):

        if word.lower() in ACRONYMS:
            titled.append(ACRONYMS[word.lower()])

        elif any(letter.isupper() for letter in word[1:]):
            titled.append(word)

        elif position > 0 and word.lower() in SMALL_WORDS:
            titled.append(word.lower())

        else:
            titled.append(word[:1].upper() + word[1:].lower())

    return " ".join(titled)


def industry_label(slug):
    """A folder slug as a heading, e.g. building_and_construction."""

    words = slug.split("_")

    return " ".join(
        word if position > 0 and word in SMALL_WORDS else word.capitalize()
        for position, word in enumerate(words)
    )


def list_documents(raw_dir=DATA_RAW_DIR):
    """Every source PDF, sorted by industry then title.

    Each entry: industry (slug), industry_label, title, path. A document filed
    under two industries appears once under each, which is how it is stored.
    Returns an empty list if the corpus folder is missing, so a clean clone
    without the data still opens the app.
    """

    root = Path(raw_dir)

    if not root.is_dir():
        return []

    documents = []

    for industry in sorted(p for p in root.iterdir() if p.is_dir()):

        for pdf in industry.rglob("*.[pP][dD][fF]"):

            documents.append(
                {
                    "industry": industry.name,
                    "industry_label": industry_label(industry.name),
                    "title": document_title(pdf.name),
                    "path": pdf,
                }
            )

    return sorted(documents, key=lambda d: (d["industry"], d["title"]))
