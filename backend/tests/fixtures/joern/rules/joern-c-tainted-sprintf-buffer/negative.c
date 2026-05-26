// negative: snprintf with explicit size bound — safe
#include <stdio.h>

void f(void) {
    char buf[64];
    snprintf(buf, sizeof(buf), "%s", "x");
}
