package org.claros.openpdfhostile;

public enum FontKind {
    NOTO_SANS("NotoSans-Regular.ttf"),
    NOTO_MATH("NotoSansMath-Regular.ttf"),
    NOTO_ARABIC("NotoSansArabic-VF.ttf"),
    NOTO_HEBREW("NotoSansHebrew-VF.ttf"),
    NOTO_CJK_SC("NotoSansSC-VF.ttf"),
    NOTO_EMOJI("NotoEmoji-VF.ttf");

    private final String fileName;

    FontKind(String fileName) {
        this.fileName = fileName;
    }

    public String fileName() {
        return fileName;
    }
}

