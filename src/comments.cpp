#include "comments.h"

#include <optional>
#include <unordered_set>

#include "flang/Parser/parse-tree.h"

inline std::string toUppercase(const std::string_view& s)
{
    std::string result;
    result.reserve(s.size());
    for (char c : s) {
        result += std::toupper(c);
    }
    return result;
}

// Extracts a comment from a line, using a state machine
std::optional<std::string> extractCommentFromLine(std::string_view line) {
    // Add more if needed
    static const std::unordered_set<std::string> DIRECTIVE_PREFIXES = {
        "!$OMP", "!$ACC", "!DIR$", "!DEC$", "!GCC$"
    };

    std::string comment;
    bool inComment = false;
    char quote = '\0';

    for (char c: line) {
        if (inComment) {
            // Escape JSON special characters
            if (c == '"' || c == '\\')
                comment += '\\';
            comment += c;
        } else if (quote == '\0' && (c == '\'' || c == '"')) {
            quote = c;
        } else if (quote != '\0' && c == quote) {
            quote = '\0';
        } else if (c == '!' && quote == '\0') {
            inComment = true;
            comment += '!';
        }

        if (DIRECTIVE_PREFIXES.count(comment) > 0) {
            comment.clear();
        }
    }

    return comment.empty() ? std::nullopt : std::optional<std::string>(comment);
}

std::vector<RawComment> extractComments(const Fortran::parser::SourceFile &file) {
    llvm::ArrayRef<char> content = file.content();
    std::vector<RawComment> comments;

    for (size_t i = 1; i <= file.lines(); i++) {
        std::size_t start = file.GetLineStartOffset(i);

        std::size_t end = start;
        while (end < content.size() && content[end] != '\n')
            end++;

        std::optional<std::string> line = extractCommentFromLine(std::string_view(content.data() + start, end - start));

        if (line.has_value()) {
            comments.push_back(RawComment{i, line.value()});
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
