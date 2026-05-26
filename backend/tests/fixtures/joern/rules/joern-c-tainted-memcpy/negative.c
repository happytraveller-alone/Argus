// negative: memcpy size is sizeof(dst) — compile-time bounded, excluded
#include <string.h>

void f(void) {
    char dst[64];
    char src[64];
    memcpy(dst, src, sizeof(dst));
}
