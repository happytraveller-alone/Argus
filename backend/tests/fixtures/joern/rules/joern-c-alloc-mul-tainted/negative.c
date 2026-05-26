// negative: both factors are literals/sizeof — compile-time foldable, excluded
#include <stdlib.h>

void *f(void) {
    return malloc(16 * sizeof(int));
}
