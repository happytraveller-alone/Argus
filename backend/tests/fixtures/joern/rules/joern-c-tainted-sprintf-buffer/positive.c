// positive: sprintf with tainted value argument — potential overflow
#include <stdio.h>
extern char *getenv(const char *);

void f(void) {
    char buf[16];
    char *u = getenv("X");
    sprintf(buf, "%s", u);
}
