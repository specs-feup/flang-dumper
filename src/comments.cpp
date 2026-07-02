#include "comments.h"

#include <optional>

#include "flang/Parser/parse-tree.h"

inline std::string_view trim(const std::string_view& s)
{
    size_t start = s.find_first_not_of(" \t");
    size_t end = s.find_last_not_of(" \t") + 1;
    return s.substr(start, end - start);
}

inline std::string escapeComment(const std::string_view& s)
{
    std::string result;
    result.reserve(s.size());
    for (char c : s) {
        if (c == '"') {
            result += "\\\"";
        } else if (c == '\\') {
            result += "\\\\";
        } else {
            result += c;
        }
    }
    return result;
}

std::optional<std::string> extractCommentFromLine(std::string_view line) {
    std::string_view trimmedLine = trim(line);

    if (trimmedLine.size() > 0 && trimmedLine[0] == '!') {
        return escapeComment(trimmedLine);
    } else {
        return std::nullopt;
    }
}

std::vector<Comment> extractComments(const Fortran::parser::SourceFile &file) {
    llvm::ArrayRef<char> content = file.content();
    std::vector<Comment> comments;

    for (size_t i = 1; i <= file.lines(); i++) {
        std::size_t start = file.GetLineStartOffset(i);

        std::size_t end = start;
        while (end < content.size() && content[end] != '\n')
            end++;

        std::optional<std::string> line = extractCommentFromLine(std::string_view(content.data() + start, end - start));

        if (line.has_value()) {
            comments.push_back(Comment{i, start + 1, line.value()});
        }
    }

    return comments;
}

std::string toString(const Comment &comment) {
    return "{\"line\": " + std::to_string(comment.line) +
           ", \"column\": " + std::to_string(comment.column) +
           ", \"text\": \"" + comment.text + "\"}";
}
