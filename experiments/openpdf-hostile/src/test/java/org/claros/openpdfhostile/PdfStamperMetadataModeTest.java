package org.claros.openpdfhostile;

import org.junit.jupiter.api.Test;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.PDPage;
import org.openpdf.text.pdf.PdfReader;
import org.openpdf.text.pdf.PdfStamper;

import java.io.ByteArrayOutputStream;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

final class PdfStamperMetadataModeTest {
    @Test
    void incrementalModePreservesInfoWhileDefaultRewriteChangesProducer() throws Exception {
        byte[] source = sourcePdf();
        Map<String, String> sourceInfo = info(source);

        ByteArrayOutputStream rewrittenBytes = new ByteArrayOutputStream();
        try (PdfReader reader = new PdfReader(source);
             PdfStamper stamper = new PdfStamper(reader, rewrittenBytes)) {
            mark(stamper);
        }
        assertNotEquals(sourceInfo.get("Producer"), info(rewrittenBytes.toByteArray()).get("Producer"));

        ByteArrayOutputStream incrementalBytes = new ByteArrayOutputStream();
        try (PdfReader reader = new PdfReader(source);
             PdfStamper stamper = new PdfStamper(reader, incrementalBytes, null, true)) {
            stamper.setUpdateDocInfo(false);
            stamper.setUpdateMetadata(false);
            mark(stamper);
        }
        assertEquals(sourceInfo, info(incrementalBytes.toByteArray()));
    }

    private static void mark(PdfStamper stamper) {
        var canvas = stamper.getOverContent(1);
        canvas.rectangle(10, 10, 2, 2);
        canvas.fill();
    }

    private static Map<String, String> info(byte[] pdf) throws Exception {
        try (PDDocument document = Loader.loadPDF(pdf)) {
            PDDocumentInformation documentInfo = document.getDocumentInformation();
            Map<String, String> values = new LinkedHashMap<>();
            for (String key : new TreeSet<>(documentInfo.getMetadataKeys())) {
                Object value = documentInfo.getPropertyStringValue(key);
                values.put(key, value == null ? "" : value.toString());
            }
            return Map.copyOf(values);
        }
    }

    private static byte[] sourcePdf() throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDDocumentInformation info = new PDDocumentInformation();
            info.setTitle("Metadata mode probe");
            info.setCreator("Claros hostile-PDF harness");
            info.setProducer("Apache PDFBox synthetic source");
            document.setDocumentInformation(info);
            document.save(output);
        }
        return output.toByteArray();
    }
}
