#include "comments.h"

#include <cassert>
#include <string>

int main() {
    const std::string sourceText = R"(! says "hello" at C:\path)";
    const RawComment rawComment{3, sourceText, 0};
    const Comment comment = processComment(rawComment, "stmt-3", 3);

    assert(comment.text == sourceText);
    assert(toString(comment) ==
           R"({"text": "! says \"hello\" at C:\\path", "stmtId": "stmt-3", "trailing": true})");

    const std::string controls = [] {
        std::string value;
        for (unsigned char c = 0; c < 0x20; ++c) {
            value += static_cast<char>(c);
        }
        return value;
    }();
    const Comment controlComment{controls, "id\"\\", false};
    const std::string escapedControls =
            "\\u0000\\u0001\\u0002\\u0003\\u0004\\u0005\\u0006\\u0007\\u0008"
            "\\t\\n\\u000b\\u000c\\r\\u000e\\u000f\\u0010\\u0011\\u0012\\u0013"
            "\\u0014\\u0015\\u0016\\u0017\\u0018\\u0019\\u001a\\u001b\\u001c"
            "\\u001d\\u001e\\u001f";
    assert(toString(controlComment) ==
           "{\"text\": \"" + escapedControls +
                   "\", \"stmtId\": \"id\\\"\\\\\", \"trailing\": false}");

    const Comment ordinaryComment{"! ordinary comment", "node-42", false};
    assert(toString(ordinaryComment) ==
           R"({"text": "! ordinary comment", "stmtId": "node-42", "trailing": false})");
}
