// negative: strcpy from string literal — excluded by rule (literal src)
#include <string.h>

void f(void) {
    char buf[16];
    strcpy(buf, "literal");
}
