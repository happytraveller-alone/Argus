// positive: malloc argument is product with tainted (atoi/getenv) factor
#include <stdlib.h>
extern int atoi(const char *);
extern char *getenv(const char *);

void *f(void) {
    int n = atoi(getenv("N"));
    return malloc(n * sizeof(int));
}
