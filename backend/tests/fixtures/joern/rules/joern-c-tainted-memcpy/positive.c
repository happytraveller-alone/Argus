// positive: memcpy size is non-literal non-sizeof; src tainted via recv
extern long recv(int, char *, long, int);

void f(int fd) {
    char dst[64];
    char src[256];
    long n;
    recv(fd, src, sizeof(src), 0);
    memcpy(dst, src, n);
}
