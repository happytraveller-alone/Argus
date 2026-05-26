// positive: strcpy from tainted (getenv) source — unbounded copy
#include <string.h>
extern char *getenv(const char *);

void f(void) {
    char buf[16];
    char *src = getenv("X");
    strcpy(buf, src);
}
