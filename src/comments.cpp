#include "comments.h"

#include "flang/Parser/parse-tree.h"

std::vector<Comment> extractComments(const Fortran::parser::SourceFile &file) {
    llvm::ArrayRef<char> content = file.content();
    std::vector<Comment> comments;

    for (size_t i = 1; i <= file.lines(); i++) {
        std::size_t start = file.GetLineStartOffset(i);

        std::size_t end = start;
        while (end < content.size() && content[end] != '\n')
            end++;

        std::string_view line(content.data() + start, end - start);

        comments.push_back(Comment{i, start + 1, line});
    }

    return comments;
}

std::string escapeQuotes(std::string_view sv) {
    std::string out;
    out.reserve(sv.size());

    for (char c : sv) {
        if (c == '"')
            out += "\\\"";
        else
            out += c;
    }
    return out;
}

std::string toString(const Comment &comment) {
    return "{\"line\": " + std::to_string(comment.line) +
           ", \"column\": " + std::to_string(comment.column) +
           ", \"text\": \"" + escapeQuotes(comment.text) + "\"}";
}
