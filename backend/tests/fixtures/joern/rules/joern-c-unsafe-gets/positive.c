// positive: gets() has no bounds check — always unsafe
#include <stdio.h>

void f(void) {
    char buf[16];
    gets(buf);
}
