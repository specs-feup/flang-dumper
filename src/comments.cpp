#include "comments.h"

#include <optional>
#include <unordered_set>

#include "flang/Parser/parse-tree.h"

// Extracts a comment from a line, using a state machine
std::tuple<std::optional<std::string>, size_t> extractCommentFromLine(std::string_view line, bool isFixedForm) {
    // Add more if needed
    static const std::unordered_set<std::string> DIRECTIVE_PREFIXES = {
        "$OMP", "$ACC", "DIR$", "DEC$", "GCC$"
    };

    if (isFixedForm) {
        char firstChar = line.empty() ? '\0' : line[0];
        if (firstChar == 'C' || firstChar == 'c' || firstChar == '*' || firstChar == 'D' || firstChar == 'd') {
            return std::make_tuple(std::optional<std::string>(line.substr(1)), 0);
        }
    }

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

std::vector<RawComment> extractComments(const Fortran::parser::SourceFile &file, const std::string &extension) {
    llvm::ArrayRef<char> content = file.content();
    std::vector<RawComment> comments;
    bool isFixedForm = extension == "f" || extension == "for";

    for (size_t i = 1; i <= file.lines(); i++) {
        std::size_t start = file.GetLineStartOffset(i);

        std::size_t end = start;
        while (end < content.size() && content[end] != '\n')
            end++;

        auto [commentOpt, sepsBefore] = extractCommentFromLine(std::string_view(content.data() + start, end - start), isFixedForm);

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
