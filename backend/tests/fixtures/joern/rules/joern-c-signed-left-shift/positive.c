// positive: left shift on signed int with non-literal operand — undefined behavior
void f(int x) {
    int y = x << 24;
}
