t = int(input())
for _ in range(t):
    s = input()
    for i in range(len(s)):
        if (s[i]=='0'):
            if i == 0:
                s = s[i+1:]
            elif i == len(s)-1:
                s= s[:i]
            else:
                s = s[:i]+s[i+1:]
            break
    for i in range(len(s)):
        if (s[i]=='1'):
            if i == 0:
                s = s[i+1:]
            elif i == len(s)-1:
                s= s[:i]
            else:
                s = s[:i]+s[i+1:]
            break
    print(s)