// negative: explicit null terminator written within next 5 statements — excluded
#include <string.h>

void f(char *src) {
    char buf[16];
    strncpy(buf, src, sizeof(buf));
    buf[15] = '\0';
}
