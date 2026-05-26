// negative: strlen result assigned to unsigned long — same width as size_t, safe
extern unsigned long strlen(const char *);

void f(const char *s) {
    unsigned long n;
    n = strlen(s);
}
