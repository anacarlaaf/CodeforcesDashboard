#include <bits/stdc++.h>
 
using namespace std;
 
int main(){
    int long long n;
    cin >> n;
    while (n >= 1){
        if (n==1){
            cout << n << endl;
            n--;
        } else {
            cout << n << " ";
            if (n % 2 == 0){
                n /= 2;
            } else {
                n = n*3 + 1;
            }
        }
    }
}