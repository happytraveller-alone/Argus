// negative: fgets with explicit bound — safe
#include <stdio.h>

void f(void) {
    char buf[16];
    fgets(buf, sizeof(buf), stdin);
}
