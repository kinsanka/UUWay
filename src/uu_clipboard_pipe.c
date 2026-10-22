/* Private stdio transport. No clipboard content is logged or written to disk. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>
#include <fcntl.h>
#include <io.h>
#define LIMIT (4u*1024u*1024u)
static HWND owner;
static int exact(void *p,size_t n) {return fread(p,1,n,stdin)==n;}
static void get(DWORD previous) {
    DWORD seq=GetClipboardSequenceNumber();
    if(seq==previous){printf("U %lu\n",seq);return;}
    if(!OpenClipboard(owner)){printf("E busy\n");return;}
    HANDLE h=GetClipboardData(CF_UNICODETEXT); const WCHAR *s=h?GlobalLock(h):0;
    SIZE_T bytes=h?GlobalSize(h):0; int n=0;
    if(s && bytes>=2 && bytes<=LIMIT*2 && wmemchr(s,0,bytes/2)) n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,s,-1,0,0,0,0);
    if(n>0 && (unsigned)n<=LIMIT+1){
        char *out=malloc(n);
        if(out && WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,s,-1,out,n,0,0)==n){printf("D %lu %d\n",seq,n-1);fwrite(out,1,n-1,stdout);}
        else printf("E conversion\n");
        free(out);
    } else printf("N %lu\n",seq);
    if(s)GlobalUnlock(h);
    CloseClipboard();
}
static void put(unsigned n) {
    if(n>LIMIT){printf("E limit\n");exit(2);}
    char *s=malloc(n+1); if(!s || !exact(s,n)){free(s);exit(2);}s[n]=0;
    if(memchr(s,0,n)){free(s);printf("E nul\n");return;}
    int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,n,0,0);
    if(n && !count){free(s);printf("E utf8\n");return;}
    HGLOBAL h=GlobalAlloc(GMEM_MOVEABLE,((size_t)count+1)*sizeof(WCHAR));
    WCHAR *w=h?GlobalLock(h):0;
    if(!w){free(s);if(h)GlobalFree(h);printf("E memory\n");return;}
    if(count)MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,n,w,count);
    w[count]=0;GlobalUnlock(h);free(s);
    if(!OpenClipboard(owner)){GlobalFree(h);printf("E busy\n");return;}
    if(!EmptyClipboard() || !SetClipboardData(CF_UNICODETEXT,h)){GlobalFree(h);printf("E set\n");}
    else printf("O %lu\n",GetClipboardSequenceNumber());
    CloseClipboard();
}
static DWORD WINAPI commands(void *unused) {
    (void)unused;
    char line[80];
    while(fgets(line,sizeof(line),stdin)){
        unsigned long n=0; char tail;
        if(sscanf(line,"G %lu %c",&n,&tail)==1)get((DWORD)n);
        else if(sscanf(line,"S %lu %c",&n,&tail)==1)put((unsigned)n);
        else if(!strcmp(line,"Q\n"))break;
        else {printf("E command\n");fflush(stdout);break;}
        fflush(stdout);
    }
    return 0;
}
int main(void) {
    _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
    owner=CreateWindowExW(0,L"STATIC",L"UU text clipboard transport",0,0,0,0,0,HWND_MESSAGE,0,GetModuleHandleW(0),0);
    if(!owner)return 1;
    HANDLE reader=CreateThread(0,0,commands,0,0,0);
    if(!reader)return 1;
    /* Wine's clipboard/X11 driver must dispatch messages even while stdin is
       idle; otherwise another client can block requesting its selection. */
    while(MsgWaitForMultipleObjects(1,&reader,FALSE,INFINITE,QS_ALLINPUT)==WAIT_OBJECT_0+1){
        MSG m;while(PeekMessageW(&m,0,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}
    }
    CloseHandle(reader);DestroyWindow(owner);return 0;
}
