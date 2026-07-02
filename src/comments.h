#ifndef __COMMENTS_H__
#define __COMMENTS_H__

#include <cstdint>
#include <string>
#include <vector>

#include "flang/Parser/source.h"

struct RawComment {
    size_t line;
    size_t column;  // TODO(Process-ing): See if this is necessary
    std::string text;
};

struct Comment {
    size_t line;
    std::string text;
    std::string parentId;
    std::string beforeId;
};

std::vector<RawComment> extractComments(const Fortran::parser::SourceFile &file);
Comment processComment(const RawComment &rawComment, const std::string &parentId, const std::string &beforeId);
std::string toString(const Comment& comment);

#endif  // __COMMENTS_H__
