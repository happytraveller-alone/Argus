// negative: left shift on unsigned int — well-defined, excluded
void f(unsigned int x) {
    unsigned int y = x << 24;
}
