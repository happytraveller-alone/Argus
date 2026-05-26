// positive: strncpy with n==sizeof(dest), no null terminator written after
#include <string.h>

void f(char *src) {
    char buf[16];
    strncpy(buf, src, sizeof(buf));
}
