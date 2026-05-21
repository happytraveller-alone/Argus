#include <stdlib.h>
#include <string.h>

static void unchecked_strcpy(char *src) {
  char dst[8];
  strcpy(dst, src);
}

static void unchecked_strcat(char *src) {
  char dst[16] = "prefix";
  strcat(dst, src);
}

static void checked_strncpy(char *src) {
  char dst[8];
  strncpy(dst, src, sizeof(dst) - 1);
  dst[sizeof(dst) - 1] = '\0';
}

static void checked_strncat(char *src) {
  char dst[16] = "prefix";
  strncat(dst, src, sizeof(dst) - strlen(dst) - 1);
}


static void overflowing_memcpy(char *src) {
  char dst[8];
  memcpy(dst, src, 64);
}

static void suspicious_sizeof_copy(char src[16]) {
  char dst[8];
  memcpy(dst, src, sizeof(src));
}

static void pointer_scale_bad(void) {
  int values[8] = {0};
  int *p = values;
  int *bad = p + sizeof(int);
  *bad = 1;
}

static int *escaped_global;

static void stack_address_escape_bad(void) {
  int local = 1;
  escaped_global = &local;
}

static void double_free_bad(void) {
  char *p = (char *)malloc(16);
  free(p);
  free(p);
}

static void use_after_free_bad(void) {
  char *p = (char *)malloc(16);
  free(p);
  p[0] = 'x';
}

static void tainted_integer_overflow(int count) {
  int bytes = count * 4096;
  char *allocated = (char *)malloc(bytes);
  free(allocated);
}

int main(int argc, char **argv) {
  if (argc > 1) {
    unchecked_strcpy(argv[1]);
    unchecked_strcat(argv[1]);
    checked_strncpy(argv[1]);
    checked_strncat(argv[1]);
    overflowing_memcpy(argv[1]);
    suspicious_sizeof_copy(argv[1]);
    pointer_scale_bad();
    stack_address_escape_bad();
    double_free_bad();
    use_after_free_bad();
    tainted_integer_overflow(atoi(argv[1]));
  }

  return 0;
}
