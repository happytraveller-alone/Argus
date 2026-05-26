// positive: strlen result assigned to int — truncation from size_t to signed 32-bit
extern unsigned long strlen(const char *);

void f(const char *s) {
    int n;
    n = strlen(s);
}
