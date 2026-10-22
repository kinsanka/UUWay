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
/* All HWNDs belong to this Wine server/prefix. Never close a window or stop its
   owner: only hide Wine explorer's legacy tray host, keeping UU's tray alive. */
static BOOL CALLBACK hide_tray(HWND window, LPARAM context) {
    WCHAR cls[64], image[1024]; DWORD pid=0, size=1024;
    (void)context;
    if(!GetClassNameW(window,cls,64) || wcscmp(cls,L"Shell_TrayWnd"))return TRUE;
    GetWindowThreadProcessId(window,&pid);
    HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);
    if(!process)return TRUE;
    BOOL found=QueryFullProcessImageNameW(process,0,image,&size);
    CloseHandle(process);
    const WCHAR *base=found?wcsrchr(image,L'\\'):0;
    if(base && !_wcsicmp(base+1,L"explorer.exe") && IsWindowVisible(window))ShowWindowAsync(window,SW_HIDE);
    return TRUE;
}
static VOID CALLBACK hide_tray_timer(HWND window,UINT message,UINT_PTR id,DWORD tick) {
    (void)window;(void)message;(void)id;(void)tick;
    EnumWindows(hide_tray,0);
}
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
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--hide-tray-once")){EnumWindows(hide_tray,0);return 0;}
    if(argc!=1)return 2;
    _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
    owner=CreateWindowExW(0,L"STATIC",L"UU text clipboard transport",0,0,0,0,0,HWND_MESSAGE,0,GetModuleHandleW(0),0);
    if(!owner)return 1;
    if(!getenv("UUWAY_SHOW_WINE_TRAY")){EnumWindows(hide_tray,0);SetTimer(owner,1,1000,hide_tray_timer);}
    HANDLE reader=CreateThread(0,0,commands,0,0,0);
    if(!reader)return 1;
    /* Wine's clipboard/X11 driver must dispatch messages even while stdin is
       idle; otherwise another client can block requesting its selection. */
    while(MsgWaitForMultipleObjects(1,&reader,FALSE,INFINITE,QS_ALLINPUT)==WAIT_OBJECT_0+1){
        MSG m;while(PeekMessageW(&m,0,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}
    }
    CloseHandle(reader);DestroyWindow(owner);return 0;
}
