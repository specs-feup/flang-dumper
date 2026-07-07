#ifndef __COMMENTS_H__
#define __COMMENTS_H__

#include <cstdint>
#include <string>
#include <vector>

#include "flang/Parser/source.h"

struct RawComment {
    size_t line;
    std::string text;
};

struct Comment {
    std::string text;
    std::string stmtId;
    bool trailing;
};

std::vector<RawComment> extractComments(const Fortran::parser::SourceFile &file);
Comment processComment(const RawComment &rawComment, const std::string &stmtId, std::size_t stmtLine);
std::string toString(const Comment& comment);

#endif  // __COMMENTS_H__
