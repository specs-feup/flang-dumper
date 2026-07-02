#ifndef __COMMENTS_H__
#define __COMMENTS_H__

#include <cstdint>
#include <string>
#include <vector>

#include "flang/Parser/source.h"

struct Comment {
    size_t line;
    size_t column;  // TODO(Process-ing): See if this is necessary
    std::string text;
};

std::vector<Comment> extractComments(const Fortran::parser::SourceFile &file);
std::string toString(const Comment& comment);

#endif  // __COMMENTS_H__
