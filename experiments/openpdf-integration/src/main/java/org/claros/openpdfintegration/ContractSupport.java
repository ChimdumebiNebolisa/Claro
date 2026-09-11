package org.claros.openpdfintegration;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

final class ContractSupport {
    static final ObjectMapper MAPPER = new ObjectMapper()
            .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    private static final Pattern DIGEST = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern OPAQUE_ID = Pattern.compile("[a-z0-9][a-z0-9_-]{7,95}");

    private ContractSupport() {
    }

    static Job readJob(Path path) throws IOException, ContractException {
        if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
            throw new ContractException("invalid_contract");
        }
        JsonNode parsed = MAPPER.readTree(Files.readAllBytes(path));
        ObjectNode root = object(parsed);
        keys(root, Set.of("schema_version", "operation", "job_id", "source", "limits",
                "font_id", "font_sha256", "pages", "answers"));
        if (integer(root, "schema_version", 1, 1) != 1 || !"render".equals(text(root, "operation", 16))) {
            throw new ContractException("invalid_contract");
        }
        String jobId = opaqueId(root, "job_id");

        ObjectNode sourceNode = object(root.required("source"));
        keys(sourceNode, Set.of("source_id", "sha256", "size_bytes", "page_count",
                "physical_ir_sha256", "evidence_version"));
        Source source = new Source(
                opaqueId(sourceNode, "source_id"),
                digest(sourceNode, "sha256"),
                integer(sourceNode, "size_bytes", 1, Integer.MAX_VALUE),
                integer(sourceNode, "page_count", 1, 10_000),
                digest(sourceNode, "physical_ir_sha256"),
                text(sourceNode, "evidence_version", 256));

        ObjectNode limitsNode = object(root.required("limits"));
        keys(limitsNode, Set.of("max_input_bytes", "max_output_bytes", "max_pages"));
        Limits limits = new Limits(
                integer(limitsNode, "max_input_bytes", 1, Integer.MAX_VALUE),
                integer(limitsNode, "max_output_bytes", 1, Integer.MAX_VALUE),
                integer(limitsNode, "max_pages", 1, 10_000));
        if (source.sizeBytes() > limits.maxInputBytes() || source.pageCount() > limits.maxPages()) {
            throw new ContractException("resource_limit");
        }
        if (!"noto-sans-regular-v1".equals(text(root, "font_id", 64))) {
            throw new ContractException("font_not_allowlisted");
        }
        String fontSha256 = digest(root, "font_sha256");

        ArrayNode pagesNode = array(root.required("pages"));
        if (pagesNode.size() != source.pageCount()) {
            throw new ContractException("invalid_contract");
        }
        List<PageGeometry> pages = new ArrayList<>();
        for (int index = 0; index < pagesNode.size(); index++) {
            ObjectNode page = object(pagesNode.get(index));
            keys(page, Set.of("page_number", "media_box_mpt", "crop_box_mpt", "rotation",
                    "user_unit", "canonical_to_pdf_mpt"));
            int pageNumber = integer(page, "page_number", 1, source.pageCount());
            if (pageNumber != index + 1) {
                throw new ContractException("invalid_contract");
            }
            int rotation = integer(page, "rotation", 0, 270);
            if (rotation % 90 != 0) {
                throw new ContractException("invalid_contract");
            }
            double userUnit;
            try {
                userUnit = Double.parseDouble(text(page, "user_unit", 32));
            } catch (NumberFormatException error) {
                throw new ContractException("invalid_contract");
            }
            if (!Double.isFinite(userUnit) || userUnit <= 0) {
                throw new ContractException("invalid_contract");
            }
            pages.add(new PageGeometry(
                    pageNumber,
                    integers(page.required("media_box_mpt"), 4),
                    integers(page.required("crop_box_mpt"), 4),
                    rotation,
                    userUnit,
                    integers(page.required("canonical_to_pdf_mpt"), 6)));
        }

        ArrayNode answersNode = array(root.required("answers"));
        if (answersNode.isEmpty() || answersNode.size() > 40) {
            throw new ContractException("invalid_contract");
        }
        List<Answer> answers = new ArrayList<>();
        Set<String> questionIds = new java.util.HashSet<>();
        for (JsonNode item : answersNode) {
            ObjectNode answer = object(item);
            keys(answer, Set.of("question_id", "display_identifier", "committed_text",
                    "committed_text_sha256", "placement_hash", "placement_classification",
                    "page_number", "lines", "continuation"));
            String questionId = opaqueId(answer, "question_id");
            if (!questionIds.add(questionId)) {
                throw new ContractException("invalid_contract");
            }
            String committedText = text(answer, "committed_text", 1_048_576);
            if (committedText.isEmpty() || !sha256(committedText.getBytes(StandardCharsets.UTF_8))
                    .equals(digest(answer, "committed_text_sha256"))) {
                throw new ContractException("invalid_contract");
            }
            if (containsRtl(committedText)) {
                throw new ContractException("unsupported_rtl");
            }
            String classification = text(answer, "placement_classification", 16);
            if (!classification.equals("inline") && !classification.equals("appendix")) {
                throw new ContractException("invalid_contract");
            }
            ArrayNode linesNode = array(answer.required("lines"));
            List<Line> lines = new ArrayList<>();
            StringBuilder reconstructed = new StringBuilder();
            for (JsonNode lineItem : linesNode) {
                ObjectNode line = object(lineItem);
                keys(line, Set.of("text", "separator_after", "x_mpt", "baseline_y_mpt",
                        "font_size_mpt"));
                String lineText = text(line, "text", 16_384);
                String separator = text(line, "separator_after", 1);
                if (lineText.isEmpty() || !(separator.isEmpty() || separator.equals(" ")
                        || separator.equals("\n"))) {
                    throw new ContractException("invalid_contract");
                }
                lines.add(new Line(
                        lineText,
                        separator,
                        integer(line, "x_mpt", 0, Integer.MAX_VALUE),
                        integer(line, "baseline_y_mpt", 0, Integer.MAX_VALUE),
                        integer(line, "font_size_mpt", 1_000, 72_000)));
                reconstructed.append(lineText).append(separator);
            }
            Continuation continuation = null;
            JsonNode continuationNode = answer.required("continuation");
            if (!continuationNode.isNull()) {
                ObjectNode value = object(continuationNode);
                keys(value, Set.of("worksheet_title", "source_question", "source_page_number",
                        "paragraphs"));
                ArrayNode paragraphNodes = array(value.required("paragraphs"));
                if (paragraphNodes.isEmpty()) {
                    throw new ContractException("invalid_contract");
                }
                List<String> paragraphs = new ArrayList<>();
                for (JsonNode paragraph : paragraphNodes) {
                    if (!paragraph.isTextual() || paragraph.textValue().isEmpty()
                            || paragraph.textValue().length() > 262_144) {
                        throw new ContractException("invalid_contract");
                    }
                    paragraphs.add(paragraph.textValue());
                }
                continuation = new Continuation(
                        text(value, "worksheet_title", 256),
                        text(value, "source_question", 32_768),
                        integer(value, "source_page_number", 1, source.pageCount()),
                        List.copyOf(paragraphs));
            }
            if (classification.equals("inline")) {
                if (lines.isEmpty() || continuation != null
                        || !reconstructed.toString().equals(committedText)) {
                    throw new ContractException("invalid_contract");
                }
            } else if (!lines.isEmpty() || continuation == null
                    || !String.join("\n\n", continuation.paragraphs()).equals(committedText)) {
                throw new ContractException("invalid_contract");
            }
            answers.add(new Answer(
                    questionId,
                    text(answer, "display_identifier", 256),
                    committedText,
                    digest(answer, "committed_text_sha256"),
                    digest(answer, "placement_hash"),
                    classification,
                    integer(answer, "page_number", 1, source.pageCount()),
                    List.copyOf(lines),
                    continuation));
        }
        return new Job(jobId, source, limits, fontSha256, List.copyOf(pages), List.copyOf(answers));
    }

    static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    static String sha256(Path path) throws IOException {
        try (var input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    static boolean containsRtl(String text) {
        return text.codePoints().anyMatch(codePoint -> {
            byte direction = Character.getDirectionality(codePoint);
            return direction == Character.DIRECTIONALITY_RIGHT_TO_LEFT
                    || direction == Character.DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC
                    || direction == Character.DIRECTIONALITY_ARABIC_NUMBER;
        });
    }

    private static ObjectNode object(JsonNode value) throws ContractException {
        if (!(value instanceof ObjectNode object)) {
            throw new ContractException("invalid_contract");
        }
        return object;
    }

    private static ArrayNode array(JsonNode value) throws ContractException {
        if (!(value instanceof ArrayNode array)) {
            throw new ContractException("invalid_contract");
        }
        return array;
    }

    private static void keys(ObjectNode value, Set<String> expected) throws ContractException {
        Set<String> actual = new java.util.HashSet<>();
        value.fieldNames().forEachRemaining(actual::add);
        if (!actual.equals(expected)) {
            throw new ContractException("invalid_contract");
        }
    }

    private static String text(ObjectNode value, String field, int maximum) throws ContractException {
        JsonNode node = value.required(field);
        if (!node.isTextual() || node.textValue().length() > maximum) {
            throw new ContractException("invalid_contract");
        }
        return node.textValue();
    }

    private static String digest(ObjectNode value, String field) throws ContractException {
        String result = text(value, field, 64);
        if (!DIGEST.matcher(result).matches()) {
            throw new ContractException("invalid_contract");
        }
        return result;
    }

    private static String opaqueId(ObjectNode value, String field) throws ContractException {
        String result = text(value, field, 96);
        if (!OPAQUE_ID.matcher(result).matches()) {
            throw new ContractException("invalid_contract");
        }
        return result;
    }

    private static int integer(ObjectNode value, String field, int minimum, int maximum)
            throws ContractException {
        JsonNode node = value.required(field);
        if (!node.isIntegralNumber() || !node.canConvertToInt()) {
            throw new ContractException("invalid_contract");
        }
        int result = node.intValue();
        if (result < minimum || result > maximum) {
            throw new ContractException("invalid_contract");
        }
        return result;
    }

    private static int[] integers(JsonNode value, int length) throws ContractException {
        ArrayNode array = array(value);
        if (array.size() != length) {
            throw new ContractException("invalid_contract");
        }
        int[] result = new int[length];
        for (int index = 0; index < length; index++) {
            JsonNode node = array.get(index);
            if (!node.isIntegralNumber() || !node.canConvertToInt()) {
                throw new ContractException("invalid_contract");
            }
            result[index] = node.intValue();
        }
        return result;
    }

    record Job(String jobId, Source source, Limits limits, String fontSha256,
               List<PageGeometry> pages, List<Answer> answers) {
    }

    record Source(String sourceId, String sha256, int sizeBytes, int pageCount,
                  String physicalIrSha256, String evidenceVersion) {
    }

    record Limits(int maxInputBytes, int maxOutputBytes, int maxPages) {
    }

    record PageGeometry(int pageNumber, int[] mediaBoxMpt, int[] cropBoxMpt, int rotation,
                        double userUnit, int[] transform) {
    }

    record Line(String text, String separatorAfter, int xMpt, int baselineYMpt,
                int fontSizeMpt) {
    }

    record Continuation(String worksheetTitle, String sourceQuestion, int sourcePageNumber,
                        List<String> paragraphs) {
    }

    record Answer(String questionId, String displayIdentifier, String committedText,
                  String committedTextSha256, String placementHash, String classification,
                  int pageNumber, List<Line> lines, Continuation continuation) {
    }

    static final class ContractException extends Exception {
        private final String code;

        ContractException(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }
}
