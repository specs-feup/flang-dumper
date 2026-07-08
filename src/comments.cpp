#include "comments.h"

#include <optional>
#include <unordered_set>

#include "flang/Parser/parse-tree.h"

// Extracts a comment from a line, using a state machine
std::tuple<std::optional<std::string>, size_t> extractCommentFromLine(std::string_view line) {
    // Add more if needed
    static const std::unordered_set<std::string> DIRECTIVE_PREFIXES = {
        "!$OMP", "!$ACC", "!DIR$", "!DEC$", "!GCC$"
    };

    std::string comment;
    std::string uppercaseComment;  // For checking directives
    bool inComment = false;
    char quote = '\0';
    size_t sepsBefore = 0;

    for (char c: line) {
        if (inComment) {
            // Escape JSON special characters
            if (c == '"' || c == '\\') {
                comment += '\\';
                uppercaseComment += '\\';
            }
            comment += c;
            uppercaseComment += static_cast<char>(std::toupper(static_cast<unsigned char>(c)));

        } else if (quote == '\0') {
            if (c == '!') {
                inComment = true;
                comment += '!';
                uppercaseComment += '!';
            } else if (c == ';') {
                sepsBefore++;
            } else if (c == '"' || c == '\'') {
                quote = c;
            }
        } else if (quote != '\0' && c == quote) {
            quote = '\0';
        }

        // Ignore directives
        if (DIRECTIVE_PREFIXES.count(uppercaseComment) > 0) {
            comment.clear();
            uppercaseComment.clear();
            inComment = false;
        }
    }

    auto commentOpt = comment.empty() ? std::nullopt : std::optional<std::string>(comment);
    return std::make_tuple(commentOpt, sepsBefore);
}

std::vector<RawComment> extractComments(const Fortran::parser::SourceFile &file) {
    llvm::ArrayRef<char> content = file.content();
    std::vector<RawComment> comments;

    for (size_t i = 1; i <= file.lines(); i++) {
        std::size_t start = file.GetLineStartOffset(i);

        std::size_t end = start;
        while (end < content.size() && content[end] != '\n')
            end++;

        auto [commentOpt, sepsBefore] = extractCommentFromLine(std::string_view(content.data() + start, end - start));

        if (commentOpt.has_value()) {
            comments.push_back(RawComment{i, commentOpt.value(), sepsBefore});
        }
    }

    return comments;
}

Comment processComment(const RawComment &rawComment, const std::string &stmtId, std::size_t stmtLine) {
    return Comment {
        rawComment.text,
        stmtId,
        stmtLine == rawComment.line
    };
}

std::string toString(const Comment &comment) {
    return "{\"text\": \"" + comment.text +
           "\", \"stmtId\": \"" + comment.stmtId +
           "\", \"trailing\": " + (comment.trailing ? "true" : "false") +
           "}";
}
