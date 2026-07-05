// ── TPM 完整初始化腳本（base64，避免 ${...} 插值問題）────────────────────────
// Source: scripts_pi/deploy_http/01_tpm_full_setup.sh
const _TPM_FULL_SETUP_B64 = "IyEvdXNyL2Jpbi9lbnYgYmFzaAojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KIyAwMV90cG1fZnVsbF9zZXR1cC5zaCDigJQg5oyB5LmF5YyWIHN3dHBtIOWIneWni+WMluiFs+acrAojCiMg54m55oCn77yaCiMgICAtIHN3dHBtIOeLgOaFi+WtmOaWvCAvdmFyL2xpYi9zd3RwbS1oaWJhL3N3dHBtLXN0YXRl77yI6YeN6ZaL5qmf5L+d55WZ77yJCiMgICAtIOmmluasoeWft+ihjO+8muW7uueriyBzd3RwbSDni4DmhYsgKyBzeXN0ZW1kIOacjeWLmSArIFRQTSDph5HpkbAKIyAgIC0g6YeN6KSH5Z+36KGM77yI5Yaq562J77yJ77ya6YeN5paw6YCj5o6l5bey5pyJ54uA5oWL77yM6Lez6YGO5bey5a6M5oiQ5q2l6amfCiMgICAtIOmWi+apn+iHquWVn++8mnN3dHBtLnNlcnZpY2Ug55SxIHN5c3RlbWQg566h55CGCiMgICAtIOaMh+e0i+epqeWumu+8muWQjOS4gCBzd3RwbSDni4DmhYvmr4/mrKHnsL3lkI3ph5HpkbDnm7jlkIwKIwojIOS9v+eUqOaWueW8j++8mnN1ZG8gYmFzaCAwMV90cG1fZnVsbF9zZXR1cC5zaAojID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KCnNldCAtdW8gcGlwZWZhaWwKCkdSRUVOPSdcMDMzWzA7MzJtJzsgUkVEPSdcMDMzWzA7MzFtJzsgWUVMTE9XPSdcMDMzWzE7MzNtJzsgQ1lBTj0nXDAzM1swOzM2bSc7IE5DPSdcMDMzWzBtJwpvaygpICAgeyBlY2hvIC1lICIke0dSRUVOfeKckyAkMSR7TkN9IjsgfQplcnIoKSAgeyBlY2hvIC1lICIke1JFRH3inJcgJDEke05DfSI7IH0KaW5mbygpIHsgZWNobyAtZSAiXG4ke1lFTExPV33ilrggJDEke05DfSI7IH0Kc2tpcCgpIHsgZWNobyAtZSAiJHtDWUFOfeKGtyAkMe+8iOW3suWtmOWcqO+8jOi3s+mBju+8iSR7TkN9IjsgfQpkaWUoKSAgeyBlcnIgIiQxIjsgZWNobyAiICDihpIg6KuL5bCH5Lul5LiK6Yyv6Kqk6LK857Wm6ZaL55m86ICF5o6S5p+lIjsgZXhpdCAxOyB9CgojIOKUgOKUgCDot6/lvpHoqK3lrprvvIjlhajpg6jmjIHkuYXljJboh7MgL3Zhci9saWIvc3d0cG0taGliYe+8iSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKIyBwb255dGFpbDogL3Zhci9saWIg5pivIFVidW50dSAyMi4wNCBBcHBBcm1vciBwcm9maWxlIOmgkOioreWFgeiosei3r+W+kQpUUE1fRElSPSIvdmFyL2xpYi9zd3RwbS1oaWJhIgpUUE1fU1RBVEU9IiR7VFBNX0RJUn0vc3d0cG0tc3RhdGUiICAgIyDmjIHkuYXljJbvvJrpnZ4gL3RtcApIQU5ETEU9IjB4ODEwMDAwMDEiClRDVElfRU5WX0ZJTEU9Ii9ldGMvcHJvZmlsZS5kL2hpYmEtdHBtLnNoIgpTV1RQTV9TRVJWSUNFPSIvZXRjL3N5c3RlbWQvc3lzdGVtL3N3dHBtLnNlcnZpY2UiClRDVElfQ09ORj0iJHtUUE1fRElSfS90Y3RpLmNvbmYiICAgICAjIOS+myBzeXN0ZW1kIEVudmlyb25tZW50RmlsZSDkvb/nlKgKU1dUUE1fTE9HPSIke1RQTV9ESVJ9L3N3dHBtLmxvZyIKClRDVElfVkFMVUU9InN3dHBtOmhvc3Q9MTI3LjAuMC4xLHBvcnQ9MjMyMSIKCmVjaG8gIj09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PSIKZWNobyAiICBIaUJBLUFCIFRQTSDmjIHkuYXljJbliJ3lp4vljJbohbPmnKwiCmVjaG8gIiAgVFBNIFN0YXRlIDogJFRQTV9TVEFURSIKZWNobyAiICBIYW5kbGUgICAgOiAkSEFORExFIgplY2hvICI9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0iCgojIOKUgOKUgCBTVEFHRSAw77ya5YmN572u56K66KqNIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAppbmZvICJTVEFHRSAw77ya5YmN572u56K66KqNIgoKW1sgJEVVSUQgLWVxIDAgXV0gfHwgZGllICLoq4vku6Ugc3VkbyDln7fooYzvvJpzdWRvIGJhc2ggJDAiCgojIOiHquWLleWuieijnee8uuWwkeeahOWll+S7tu+8iOmBv+WFjemcgOimgeS9v+eUqOiAheaJi+WLleWuieijne+8iQpQS0dTX05FRURFRD0oKQpjb21tYW5kIC12IHN3dHBtICAgICAgID4vZGV2L251bGwgMj4mMSB8fCBQS0dTX05FRURFRCs9KHN3dHBtKQpjb21tYW5kIC12IHN3dHBtX3NldHVwID4vZGV2L251bGwgMj4mMSB8fCBQS0dTX05FRURFRCs9KHN3dHBtLXRvb2xzKQpjb21tYW5kIC12IHRwbTJfY3JlYXRlcHJpbWFyeSA+L2Rldi9udWxsIDI+JjEgfHwgUEtHU19ORUVERUQrPSh0cG0yLXRvb2xzKQpjb21tYW5kIC12IG9wZW5zc2wgICAgID4vZGV2L251bGwgMj4mMSB8fCBQS0dTX05FRURFRCs9KG9wZW5zc2wpCgppZiBbWyAkeyNQS0dTX05FRURFRFtAXX0gLWd0IDAgXV07IHRoZW4KICBpbmZvICLoh6rli5Xlronoo53nvLrlsJHlpZfku7bvvJoke1BLR1NfTkVFREVEWypdfSIKICBhcHQtZ2V0IHVwZGF0ZSAtcSAyPi9kZXYvbnVsbCB8fCB0cnVlCiAgYXB0LWdldCBpbnN0YWxsIC15ICIke1BLR1NfTkVFREVEW0BdfSIgXAogICAgfHwgZGllICLlpZfku7blronoo53lpLHmlZfvvIzoq4vmiYvli5Xln7fooYzvvJpzdWRvIGFwdC1nZXQgaW5zdGFsbCAteSBzd3RwbSBzd3RwbS10b29scyB0cG0yLXRvb2xzIG9wZW5zc2wiCmZpCgpmb3IgY21kIGluIHN3dHBtIHN3dHBtX3NldHVwIHRwbTJfY3JlYXRlcHJpbWFyeSB0cG0yX2NyZWF0ZSB0cG0yX2xvYWQgXAogICAgICAgICAgIHRwbTJfZXZpY3Rjb250cm9sIHRwbTJfcmVhZHB1YmxpYyB0cG0yX2ZsdXNoY29udGV4dCBvcGVuc3NsOyBkbwogIGNvbW1hbmQgLXYgIiRjbWQiID4vZGV2L251bGwgMj4mMSBcCiAgICAmJiBvayAiJGNtZCDlt7Llronoo50iIFwKICAgIHx8IGRpZSAiJGNtZCDmnKrmib7liLDvvIjlronoo53lpLHmlZfvvIkiCmRvbmUKCiMg4pSA4pSAIEFwcEFybW9yIOebuOWuueaAp++8iFVidW50dSAyMi4wNCDnmoQgc3d0cG0gYXB0IOWll+S7tumZhOW4tiBwcm9maWxl77yJIOKUgOKUgAojIHN3dHBtIOeahCBBcHBBcm1vciBwcm9maWxlIOmgkOioreS4jeWFgeioseWtmOWPliAvb3B0Lyoq77yMCiMg5pS555SoIC92YXIvbGliL3N3dHBtLWhpYmEg5Y2z54K65YWB6Kix56+E5ZyN77yM5L2G6Iul5LuN5pyJ6ZmQ5Yi25YmH5YiH5o+bIGNvbXBsYWlu44CCCmlmIGNvbW1hbmQgLXYgYWEtc3RhdHVzID4vZGV2L251bGwgMj4mMSAmJiBhYS1zdGF0dXMgLS1lbmFibGVkIDI+L2Rldi9udWxsOyB0aGVuCiAgQVBQQVJNT1JfRklYRUQ9MAogIGZvciBfcHJvZiBpbiAvZXRjL2FwcGFybW9yLmQvdXNyLmJpbi5zd3RwbSAvZXRjL2FwcGFybW9yLmQvc3d0cG0gXAogICAgICAgICAgICAgICAvZXRjL2FwcGFybW9yLmQvdXNyLnNiaW4uc3d0cG07IGRvCiAgICBpZiBbWyAtZiAiJF9wcm9mIiBdXTsgdGhlbgogICAgICBpbmZvICLlgbXmuKzliLAgQXBwQXJtb3IgcHJvZmlsZe+8miRfcHJvZiIKICAgICAgaWYgY29tbWFuZCAtdiBhYS1jb21wbGFpbiA+L2Rldi9udWxsIDI+JjE7IHRoZW4KICAgICAgICBhYS1jb21wbGFpbiAiJF9wcm9mIiAyPi9kZXYvbnVsbCBcCiAgICAgICAgICAmJiBvayAic3d0cG0gQXBwQXJtb3Ig4oaSIGNvbXBsYWluIOaooeW8j++8iOS4jeaUlOaIqu+8iSIgXAogICAgICAgICAgfHwgZXJyICJhYS1jb21wbGFpbiDlpLHmlZfvvIjnubznuozvvIzoi6Xlvoznuowgc3d0cG1fc2V0dXAg5aSx5pWX6KuL5omL5YuV5Z+36KGM77yJIgogICAgICBlbHNlCiAgICAgICAgYXBwYXJtb3JfcGFyc2VyIC1SICIkX3Byb2YiIDI+L2Rldi9udWxsIFwKICAgICAgICAgICYmIG9rICJzd3RwbSBBcHBBcm1vciBwcm9maWxlIOW3suenu+mZpCIgXAogICAgICAgICAgfHwgZXJyICJBcHBBcm1vciDnp7vpmaTlpLHmlZfvvIjnubznuozvvIkiCiAgICAgIGZpCiAgICAgIEFQUEFSTU9SX0ZJWEVEPTEKICAgICAgYnJlYWsKICAgIGZpCiAgZG9uZQogIGlmIFtbICRBUFBBUk1PUl9GSVhFRCAtZXEgMCBdXSAmJiBhYS1zdGF0dXMgMj4vZGV2L251bGwgfCBncmVwIC1xICdzd3RwbSc7IHRoZW4KICAgIGFhLWNvbXBsYWluIC91c3IvYmluL3N3dHBtICAgICAgIDI+L2Rldi9udWxsIHx8IHRydWUKICAgIGFhLWNvbXBsYWluIC91c3IvYmluL3N3dHBtX3NldHVwIDI+L2Rldi9udWxsIHx8IHRydWUKICAgIG9rICJzd3RwbSBBcHBBcm1vciDihpIgY29tcGxhaW4g5qih5byP77yIYnkgYmluYXJ577yJIgogIGZpCmZpCgojIOW7uueri+ebrumMhO+8iOaMgeS5heWMlui3r+W+ke+8iQpta2RpciAtcCAiJFRQTV9ESVIiICIkVFBNX1NUQVRFIgpSRUFMX1VTRVI9IiR7U1VET19VU0VSOi0ke1VTRVI6LSQobG9nbmFtZSAyPi9kZXYvbnVsbCB8fCB3aG9hbWkpfX0iCmNob3duIC1SIHJvb3Q6cm9vdCAiJFRQTV9ESVIiCmNobW9kIDc1NSAiJFRQTV9ESVIiCmNobW9kIDc1NSAiJFRQTV9TVEFURSIKb2sgIuebrumMhOW7uueri++8miRUUE1fRElSIgoKIyDilIDilIAgU1RBR0UgMe+8mnN3dHBtIOeLgOaFi+WIneWni+WMlu+8iOWGquetie+8muWDhemmluasoeWft+ihjO+8iSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaW5mbyAiU1RBR0UgMe+8mnN3dHBtIOeLgOaFi+WIneWni+WMliIKClNUQVRFX01BUktFUj0iJHtUUE1fU1RBVEV9Ly5pbml0aWFsaXplZCIKCmlmIFtbIC1mICIkU1RBVEVfTUFSS0VSIiBdXTsgdGhlbgogIHNraXAgInN3dHBtIOeLgOaFi+W3suWtmOWcqO+8iCRUUE1fU1RBVEXvvInvvIzot7PpgY4gc3d0cG1fc2V0dXAiCiAgZWNobyAiICDihpIg5oyH57SL6IiH6aaW5qyh5Yid5aeL5YyW55u45ZCM77yI56mp5a6a77yJIgplbHNlCiAgIyDpppbmrKHln7fooYzvvJrlu7rnq4sgc3d0cG0g54uA5oWL77yI5LiN5YqgIC0tb3ZlcndyaXRl77yM56K65L+d6YeR6ZGw5Y+q5bu65LiA5qyh77yJCiAgc3d0cG1fc2V0dXAgXAogICAgLS10cG0yIFwKICAgIC0tdHBtc3RhdGUgIiRUUE1fU1RBVEUiIFwKICAgIC0tYWxsb3ctc2lnbmluZyAyPj4iJFNXVFBNX0xPRyIgfHwgZGllICJzd3RwbV9zZXR1cCDlpLHmlZfvvIzmn6XnnIvvvJokU1dUUE1fTE9HIgoKICB0b3VjaCAiJFNUQVRFX01BUktFUiIKICBvayAic3d0cG0g54uA5oWL5Yid5aeL5YyW5a6M5oiQ77yIU2lnbmluZyBLZXkg5bey5bu656uL77yJIgpmaQoKIyDilIDilIAgU1RBR0UgMu+8muW7uueriyBzeXN0ZW1kIOacjeWLme+8iOWGquetie+8iSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaW5mbyAiU1RBR0UgMu+8mnN3dHBtIHN5c3RlbWQg5pyN5YuZIgoKIyDlr6vlhaUgRW52aXJvbm1lbnRGaWxl77yI5L6bIHN5c3RlbWQgc2VydmljZSDoroDlj5YgVENUSe+8iQpjYXQgPiAiJFRDVElfQ09ORiIgPDxFT0YKVFBNMlRPT0xTX1RDVEk9JHtUQ1RJX1ZBTFVFfQpFT0YKY2hvd24gcm9vdDpyb290ICIkVENUSV9DT05GIgpjaG1vZCA2NDQgIiRUQ1RJX0NPTkYiCm9rICJUQ1RJIOioreWumuaqlO+8miRUQ1RJX0NPTkYiCgppZiBbWyAtZiAiJFNXVFBNX1NFUlZJQ0UiIF1dOyB0aGVuCiAgc2tpcCAic3d0cG0uc2VydmljZSDlt7LlrZjlnKgiCmVsc2UKICBjYXQgPiAiJFNXVFBNX1NFUlZJQ0UiIDw8RU9GCltVbml0XQpEZXNjcmlwdGlvbj1Tb2Z0d2FyZSBUUE0gKHN3dHBtKSBmb3IgSGlCQS1BQgpBZnRlcj1uZXR3b3JrLnRhcmdldApCZWZvcmU9aGliYS1zdWJ3ZWIuc2VydmljZQoKW1NlcnZpY2VdClR5cGU9Zm9ya2luZwpVc2VyPXJvb3QKRXhlY1N0YXJ0UHJlPS9iaW4vbWtkaXIgLXAgJHtUUE1fU1RBVEV9CkV4ZWNTdGFydD0vdXNyL2Jpbi9zd3RwbSBzb2NrZXQgXFwKICAtLXRwbXN0YXRlIGRpcj0ke1RQTV9TVEFURX0gXFwKICAtLWN0cmwgdHlwZT10Y3AscG9ydD0yMzIyIFxcCiAgLS1zZXJ2ZXIgdHlwZT10Y3AscG9ydD0yMzIxIFxcCiAgLS10cG0yIFxcCiAgLS1mbGFncyBzdGFydHVwLWNsZWFyIFxcCiAgLS1kYWVtb24gXFwKICAtLWxvZyBmaWxlPSR7U1dUUE1fTE9HfSxsZXZlbD01CkV4ZWNTdG9wPS91c3IvYmluL3BraWxsIC1mICJzd3RwbSBzb2NrZXQiClJlbWFpbkFmdGVyRXhpdD15ZXMKUmVzdGFydD1vbi1mYWlsdXJlClJlc3RhcnRTZWM9MwoKW0luc3RhbGxdCldhbnRlZEJ5PW11bHRpLXVzZXIudGFyZ2V0CkVPRgogIG9rICJzd3RwbS5zZXJ2aWNlIOW7uueri+WujOaIkCIKZmkKCiMg5ZWf55So5Lim77yI6YeN77yJ5ZWf5YuVIHN3dHBtIOacjeWLmQpzeXN0ZW1jdGwgZGFlbW9uLXJlbG9hZApzeXN0ZW1jdGwgZW5hYmxlIHN3dHBtLnNlcnZpY2UKc3lzdGVtY3RsIHJlc3RhcnQgc3d0cG0uc2VydmljZQpzbGVlcCAyCgppZiBzeXN0ZW1jdGwgaXMtYWN0aXZlIC0tcXVpZXQgc3d0cG0uc2VydmljZTsgdGhlbgogIG9rICJzd3RwbS5zZXJ2aWNlIOmBi+ihjOS4rSIKZWxzZQogIGpvdXJuYWxjdGwgLXUgc3d0cG0uc2VydmljZSAtbiAyMCAtLW5vLXBhZ2VyCiAgZGllICJzd3RwbS5zZXJ2aWNlIOWVn+WLleWkseaVlyIKZmkKCiMg56K66KqNIFRDUCDpgKPmjqXln6DlsLHnt5LvvIhzcyDkuI3kuIDlrprlrZjlnKjvvIzmlLnnlKggUHl0aG9uIHNvY2tldCDmjqLmuKzvvIkKaWYgcHl0aG9uMyAtYyAiCmltcG9ydCBzb2NrZXQsIHN5cwpzID0gc29ja2V0LnNvY2tldCgpCnMuc2V0dGltZW91dCgzKQp0cnk6CiAgICBzLmNvbm5lY3QoKCcxMjcuMC4wLjEnLCAyMzIxKSkKICAgIHMuY2xvc2UoKQogICAgc3lzLmV4aXQoMCkKZXhjZXB0IEV4Y2VwdGlvbjoKICAgIHN5cy5leGl0KDEpCiIgMj4vZGV2L251bGw7IHRoZW4KICBvayAic3d0cG0gVENQIHBvcnQgMjMyMSDlsLHnt5IiCmVsaWYgcGdyZXAgLXggc3d0cG0gPi9kZXYvbnVsbCAyPiYxOyB0aGVuCiAgb2sgInN3dHBtIOeoi+W6j+WtmOWcqO+8iHBvcnQg5o6i5ris55Ww5bi477yM57m857qM5Z+36KGM77yJIgplbHNlCiAgZGllICJzd3RwbSBwb3J0IDIzMjEg5pyq5bCx57eS77yIc3d0cG0g56iL5bqP5pyq5ZWf5YuV77yJIgpmaQoKIyDilIDilIAgU1RBR0UgM++8muioreWumiBUQ1RJIOeSsOWig+iuiuaVuO+8iOezu+e1seWFqOWfn++8iSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaW5mbyAiU1RBR0UgM++8muioreWumiBUQ1RJIOeSsOWig+iuiuaVuCIKCiMgL2V0Yy9wcm9maWxlLmQv77yI5LqS5YuV5byPIHNoZWxs77yJCmNhdCA+ICIkVENUSV9FTlZfRklMRSIgPDxFT0YKIyBIaUJBLUFCIHN3dHBtIFRDVEkg4oCUIOeUsSAwMV90cG1fZnVsbF9zZXR1cC5zaCDoh6rli5XnlKLnlJ8KZXhwb3J0IFRQTTJUT09MU19UQ1RJPSIke1RDVElfVkFMVUV9IgpFT0YKY2htb2QgNjQ0ICIkVENUSV9FTlZfRklMRSIKb2sgIuezu+e1seWFqOWfn+eSsOWig+iuiuaVuO+8miRUQ1RJX0VOVl9GSUxFIgoKIyDnm67liY0gc2hlbGwgc2Vzc2lvbiDnq4vljbPnlJ/mlYgKZXhwb3J0IFRQTTJUT09MU19UQ1RJPSIkVENUSV9WQUxVRSIKCiMg6IulIGhpYmEtc3Vid2ViLnNlcnZpY2Ug5a2Y5Zyo77yM5pu05paw5YW2IEVudmlyb25tZW50RmlsZSDkvb/lhbboroDlj5YgVENUSQpTVUJXRUJfRU5WPSIvb3B0L2hpYmEvc3Vid2ViLy5lbnYiCmlmIFtbIC1mICIkU1VCV0VCX0VOViIgXV07IHRoZW4KICBzZWQgLWkgJy9eVFBNMlRPT0xTX1RDVEkvZCcgIiRTVUJXRUJfRU5WIgogIGVjaG8gIlRQTTJUT09MU19UQ1RJPSR7VENUSV9WQUxVRX0iID4+ICIkU1VCV0VCX0VOViIKICBvayAiaGliYS1zdWJ3ZWIgLmVudiDmm7TmlrAgVFBNMlRPT0xTX1RDVEkiCmZpCgojIOeiuuS/neatpCBzaGVsbCDnmoQgVENUSSDlt7LmjIflkJEgc3d0cG0KZXhwb3J0IFRQTTJUT09MU19UQ1RJPSIke1RDVElfVkFMVUV9IgoKIyDilIDilIAg5Yaq562J5a6I6KGb77ya6IulIEhhbmRsZSDlt7LmjIHkuYXljJbliYfot7PpgY4gU1RBR0VTIDQtNyDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaWYgW1sgLWYgIiRTVEFURV9NQVJLRVIiIF1dICYmIFwKICAgdHBtMl9nZXRjYXAgaGFuZGxlcy1wZXJzaXN0ZW50IDI+L2Rldi9udWxsIHwgZ3JlcCAtcSAiJEhBTkRMRSI7IHRoZW4KICBza2lwICLnsL3lkI3lr4bpkbDlt7LmjIHkuYXljJboh7MgJEhBTkRMRe+8jOi3s+mBjiBTVEFHRVMgNC0377yI5Yaq562J5L+d6K2377yJIgogICMg55u05o6l6Lez5b6AIFNUQUdFIDgKZWxzZQoKIyDilIDilIAgU1RBR0UgNO+8mua4heepuiBUUE0gY29udGV4dCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaW5mbyAiU1RBR0UgNO+8mua4heepuiBUUE0gY29udGV4dCIKCmlmIHRwbTJfY2xlYXIgLS1oaWVyYXJjaHkgb3duZXIgMj4vZGV2L251bGw7IHRoZW4KICBvayAiVFBNIOa4heepuu+8iOaWsOeJiOiqnuazle+8iSIKZWxpZiB0cG0yX2NsZWFyIC1jIG8gMj4vZGV2L251bGw7IHRoZW4KICBvayAiVFBNIOa4heepuu+8iOiIiueJiOiqnuazlSAtYyBv77yJIgplbGlmIHRwbTJfY2xlYXIgMj4vZGV2L251bGw7IHRoZW4KICBvayAiVFBNIOa4heepuu+8iOeEoeWPg+aVuO+8iSIKZWxzZQogIGVyciAidHBtMl9jbGVhciDlpLHmlZfvvIznubznuozln7fooYzvvIjpnZ7oh7Tlkb3vvIkiCmZpCgojIOKUgOKUgCBTVEFHRSA177ya5bu656uLIFByaW1hcnkgS2V5IOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAppbmZvICJTVEFHRSA177ya5bu656uLIFByaW1hcnkgS2V5IgoKcm0gLWYgIiR7VFBNX0RJUn0vcHJpbWFyeS5jdHgiCgp0cG0yX2NyZWF0ZXByaW1hcnkgXAogIC0taGllcmFyY2h5IG93bmVyIFwKICAtLWtleS1hbGdvcml0aG0gcnNhIFwKICAtLWhhc2gtYWxnb3JpdGhtIHNoYTI1NiBcCiAgLS1rZXktY29udGV4dCAiJHtUUE1fRElSfS9wcmltYXJ5LmN0eCIgfHwgZGllICJ0cG0yX2NyZWF0ZXByaW1hcnkg5aSx5pWXIgoKW1sgLXMgIiR7VFBNX0RJUn0vcHJpbWFyeS5jdHgiIF1dIFwKICAmJiBvayAicHJpbWFyeS5jdHgg5bu656uL5a6M5oiQ77yIJCh3YyAtYyA8ICIke1RQTV9ESVJ9L3ByaW1hcnkuY3R4IikgYnl0ZXPvvIkiIFwKICB8fCBkaWUgInByaW1hcnkuY3R4IOW+jOeCuuepuiIKCiMg4pSA4pSAIFNUQUdFIDbvvJrlu7rnq4sgU2lnbmluZyBLZXkg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmluZm8gIlNUQUdFIDbvvJrlu7rnq4sgUlNBLTIwNDggU2lnbmluZyBLZXkiCgpybSAtZiAiJHtUUE1fRElSfS9zaWduaW5nLnB1YiIgIiR7VFBNX0RJUn0vc2lnbmluZy5wcml2IgoKdHBtMl9jcmVhdGUgXAogIC0tcGFyZW50LWNvbnRleHQgIiR7VFBNX0RJUn0vcHJpbWFyeS5jdHgiIFwKICAtLWtleS1hbGdvcml0aG0gInJzYTIwNDg6cnNhc3NhOm51bGwiIFwKICAtLWhhc2gtYWxnb3JpdGhtIHNoYTI1NiBcCiAgLS1wdWJsaWMgICIke1RQTV9ESVJ9L3NpZ25pbmcucHViIiBcCiAgLS1wcml2YXRlICIke1RQTV9ESVJ9L3NpZ25pbmcucHJpdiIgfHwgZGllICJ0cG0yX2NyZWF0ZSDlpLHmlZciCgpbWyAtcyAiJHtUUE1fRElSfS9zaWduaW5nLnB1YiIgXV0gICYmIG9rICJzaWduaW5nLnB1YiAg5bu656uL5a6M5oiQIiB8fCBkaWUgInNpZ25pbmcucHViIOS4jeWtmOWcqCIKW1sgLXMgIiR7VFBNX0RJUn0vc2lnbmluZy5wcml2IiBdXSAmJiBvayAic2lnbmluZy5wcml2IOW7uueri+WujOaIkCIgfHwgZGllICJzaWduaW5nLnByaXYg5LiN5a2Y5ZyoIgoKIyDilIDilIAgU1RBR0UgN++8mui8ieWFpeS4puaMgeS5heWMliDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaW5mbyAiU1RBR0UgN++8mui8ieWFpemHkemRsOS4puaMgeS5heWMluiHsyAkSEFORExFIgoKdHBtMl9mbHVzaGNvbnRleHQgLS10cmFuc2llbnQtb2JqZWN0IDI+L2Rldi9udWxsIHx8IHRydWUKdHBtMl9mbHVzaGNvbnRleHQgLS1sb2FkZWQtc2Vzc2lvbiAgIDI+L2Rldi9udWxsIHx8IHRydWUKdHBtMl9mbHVzaGNvbnRleHQgLS1zYXZlZC1zZXNzaW9uICAgIDI+L2Rldi9udWxsIHx8IHRydWUKCnJtIC1mICIke1RQTV9ESVJ9L3NpZ25pbmcuY3R4IgoKdHBtMl9sb2FkIFwKICAtLXBhcmVudC1jb250ZXh0ICIke1RQTV9ESVJ9L3ByaW1hcnkuY3R4IiBcCiAgLS1wdWJsaWMgICIke1RQTV9ESVJ9L3NpZ25pbmcucHViIiBcCiAgLS1wcml2YXRlICIke1RQTV9ESVJ9L3NpZ25pbmcucHJpdiIgXAogIC0ta2V5LWNvbnRleHQgIiR7VFBNX0RJUn0vc2lnbmluZy5jdHgiIHx8IGRpZSAidHBtMl9sb2FkIOWkseaVlyIKCltbIC1zICIke1RQTV9ESVJ9L3NpZ25pbmcuY3R4IiBdXSAmJiBvayAic2lnbmluZy5jdHgg5bu656uL5a6M5oiQIiB8fCBkaWUgInNpZ25pbmcuY3R4IOS4jeWtmOWcqCIKCnRwbTJfZmx1c2hjb250ZXh0IC0tdHJhbnNpZW50LW9iamVjdCAyPi9kZXYvbnVsbCB8fCB0cnVlCgojIOa4hemZpOiIiiBIYW5kbGXvvIjoi6XlrZjlnKjvvIkKdHBtMl9ldmljdGNvbnRyb2wgXAogIC0taGllcmFyY2h5IG93bmVyIFwKICAtLW9iamVjdC1jb250ZXh0ICIkSEFORExFIiBcCiAgIiRIQU5ETEUiIDI+L2Rldi9udWxsICYmIGVjaG8gIiAgKOiIiiBIYW5kbGUg5bey5riF6ZmkKSIgfHwgdHJ1ZQoKdHBtMl9ldmljdGNvbnRyb2wgXAogIC0taGllcmFyY2h5IG93bmVyIFwKICAtLW9iamVjdC1jb250ZXh0ICIke1RQTV9ESVJ9L3NpZ25pbmcuY3R4IiBcCiAgIiRIQU5ETEUiIHx8IGRpZSAidHBtMl9ldmljdGNvbnRyb2wg5aSx5pWXIgoKb2sgIuaMgeS5heWMluWujOaIkO+8miRIQU5ETEUiCgpmaSAgIyDilIDilIAgZW5kIG9mIFNUQUdFUyA0LTfvvIjlhqrnrYnlrojooZvvvInilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKCiMg4pSA4pSAIFNUQUdFIDjvvJrljK/lh7rlhazpkbDoiIcgRUsgRmluZ2VycHJpbnQg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmluZm8gIlNUQUdFIDjvvJrljK/lh7rlhazpkbDoiIcgRUsgRmluZ2VycHJpbnQiCgp0cG0yX2ZsdXNoY29udGV4dCAtLXRyYW5zaWVudC1vYmplY3QgMj4vZGV2L251bGwgfHwgdHJ1ZQp0cG0yX2ZsdXNoY29udGV4dCAtLWxvYWRlZC1zZXNzaW9uICAgMj4vZGV2L251bGwgfHwgdHJ1ZQoKdHBtMl9yZWFkcHVibGljIFwKICAtLW9iamVjdC1jb250ZXh0ICIkSEFORExFIiBcCiAgLS1vdXRwdXQgIiR7VFBNX0RJUn0vc2lnbmluZ19wdWJsaWMucGVtIiBcCiAgLS1mb3JtYXQgcGVtIHx8IGRpZSAidHBtMl9yZWFkcHVibGljIOWkseaVlyIKCm9rICLlhazpkbDljK/lh7rvvJoke1RQTV9ESVJ9L3NpZ25pbmdfcHVibGljLnBlbSIKCkVLX0ZQPSQob3BlbnNzbCBwa2V5IC1pbiAiJHtUUE1fRElSfS9zaWduaW5nX3B1YmxpYy5wZW0iIC1wdWJpbiAtb3V0Zm9ybSBERVIgMj4vZGV2L251bGwgXAogIHwgc2hhMjU2c3VtIHwgYXdrICd7cHJpbnQgJDF9JykKZWNobyAiJEVLX0ZQIiA+ICIke1RQTV9ESVJ9L2VrX2ZpbmdlcnByaW50LnR4dCIKb2sgIkVLIEZpbmdlcnByaW5077yaJEVLX0ZQIgoKIyDilIDilIAgU1RBR0UgOe+8muacgOe1gumpl+itiSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKaW5mbyAiU1RBR0UgOe+8muacgOe1gumpl+itiSIKCnRwbTJfZmx1c2hjb250ZXh0IC0tdHJhbnNpZW50LW9iamVjdCAyPi9kZXYvbnVsbCB8fCB0cnVlCnRwbTJfZmx1c2hjb250ZXh0IC0tbG9hZGVkLXNlc3Npb24gICAyPi9kZXYvbnVsbCB8fCB0cnVlCgpIQU5ETEVTPSQodHBtMl9nZXRjYXAgaGFuZGxlcy1wZXJzaXN0ZW50IDI+L2Rldi9udWxsKQplY2hvICIkSEFORExFUyIgfCBncmVwIC1xICIkSEFORExFIiBcCiAgJiYgb2sgIkhhbmRsZSAkSEFORExFIOeiuuiqjeWtmOWcqCIgXAogIHx8IGRpZSAiSGFuZGxlIOS4jeWcqOa4heWWruS4rSIKCiMg57C956ug5ris6KmmCmVjaG8gImhpYmEtdGVzdCIgPiAvdG1wL19oaWJhX3Rlc3QudHh0CnRwbTJfc2lnbiBcCiAgLS1rZXktY29udGV4dCAiJEhBTkRMRSIgXAogIC0taGFzaC1hbGdvcml0aG0gc2hhMjU2IFwKICAtLXNjaGVtZSByc2Fzc2EgXAogIC0tc2lnbmF0dXJlIC90bXAvX2hpYmFfc2lnLmJpbiBcCiAgL3RtcC9faGliYV90ZXN0LnR4dCAyPi9kZXYvbnVsbCBcCiAgJiYgb2sgIuewveeroOa4rOippumAmumBjiIgXAogIHx8IGVyciAi57C956ug5ris6Kmm5aSx5pWX77yI6Z2e6Ie05ZG977yM5oyB5LmF5YyW5bey5oiQ5Yqf77yJIgpybSAtZiAvdG1wL19oaWJhX3Rlc3QudHh0IC90bXAvX2hpYmFfc2lnLmJpbgoKIyDilIDilIAg6IulIGhpYmEtc3Vid2ViLnNlcnZpY2Ug5bey5a6J6KOd77yM6YeN5ZWf5Lul5aWX55So5paw55Kw5aKD6K6K5pW4IOKUgOKUgOKUgOKUgOKUgOKUgAppZiBzeXN0ZW1jdGwgaXMtZW5hYmxlZCBoaWJhLXN1YndlYi5zZXJ2aWNlIDI+L2Rldi9udWxsIHwgZ3JlcCAtcSAiZW5hYmxlZCI7IHRoZW4KICBzeXN0ZW1jdGwgcmVzdGFydCBoaWJhLXN1YndlYi5zZXJ2aWNlCiAgb2sgImhpYmEtc3Vid2ViLnNlcnZpY2Ug5bey6YeN5ZWf77yI5aWX55SoIFRQTSDnkrDlooPorormlbjvvIkiCmZpCgojIOKUgOKUgCDoh6rli5XljK/lh7ogbWFjaGluZS1wdWJrZXkucGVtIOiHs+Wft+ihjOebrumMhCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKRVhQT1JUX0RJUj0iJChwd2QpIgpQVUJLRVlfRVhQT1JUPSIke0VYUE9SVF9ESVJ9L21hY2hpbmUtcHVia2V5LnBlbSIKaWYgY3AgIiR7VFBNX0RJUn0vc2lnbmluZ19wdWJsaWMucGVtIiAiJFBVQktFWV9FWFBPUlQiIDI+L2Rldi9udWxsOyB0aGVuCiAgY2hvd24gIiRSRUFMX1VTRVIiOiIkUkVBTF9VU0VSIiAiJFBVQktFWV9FWFBPUlQiIDI+L2Rldi9udWxsIHx8IHRydWUKICBvayAibWFjaGluZS1wdWJrZXkucGVtIOW3suWMr+WHuuiHs++8miRQVUJLRVlfRVhQT1JUIgplbHNlCiAgZXJyICJtYWNoaW5lLXB1YmtleS5wZW0g5Yyv5Ye65aSx5pWX77yI6Z2e6Ie05ZG977yJIgpmaQoKIyDilIDilIAg5a6M5oiQ5pGY6KaBIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICIiCmVjaG8gIj09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PSIKZWNobyAtZSAiJHtHUkVFTn0gIFRQTSDmjIHkuYXljJbliJ3lp4vljJblrozmiJDvvIEke05DfSIKZWNobyAiPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09IgplY2hvICIgIEhhbmRsZSAgICAgIDogJEhBTkRMRSIKZWNobyAiICDni4DmhYvnm67pjIQgICAgOiAkVFBNX1NUQVRF77yI6ZaL5qmf5L+d55WZ77yJIgplY2hvICIgIOWFrOmRsO+8iOezu+e1se+8iTogJHtUUE1fRElSfS9zaWduaW5nX3B1YmxpYy5wZW0iCmVjaG8gIiAg5YWs6ZGw77yI5LiK5YKz77yJOiAke1BVQktFWV9FWFBPUlR9IgplY2hvICIiCmVjaG8gIiAg5pyN5YuZ54uA5oWL77yaIgpzeXN0ZW1jdGwgaXMtYWN0aXZlIHN3dHBtLnNlcnZpY2UgICAgICAmJiBlY2hvICIgICAgc3d0cG0gICAgICA6IHJ1bm5pbmcg4pyTIiB8fCBlY2hvICIgICAgc3d0cG0gICAgICA6IEZBSUxFRCDinJciCnN5c3RlbWN0bCBpcy1lbmFibGVkIHN3dHBtLnNlcnZpY2UgICAgICYmIGVjaG8gIiAgICDplovmqZ/oh6rllZ8gICA6IGVuYWJsZWQg4pyTIiB8fCBlY2hvICIgICAg6ZaL5qmf6Ieq5ZWfICAgOiBkaXNhYmxlZCIKZWNobyAiIgplY2hvICIgIOeSsOWig+iuiuaVuO+8iOW3suWvq+WFpSAkVENUSV9FTlZfRklMRe+8ie+8miIKZWNobyAiICAgIFRQTTJUT09MU19UQ1RJPSR7VENUSV9WQUxVRX0iCmVjaG8gIiIKZWNobyAiICDkuIvkuIDmraXvvJoiCmVjaG8gIiAgICDlsIcgbWFjaGluZS1wdWJrZXkucGVtIOS4iuWCs+iHsyBLaXQgQ29tcG9zZXIg5bmz5Y+w5Lul5Y+W5b6X5qmf5Zmo57aB5a6a5o6I5qyKIgplY2hvICIgICAg77yI5oiW5Z+36KGMIGdldC1tYWNoaW5lLXB1YmtleS5zaCDph43mlrDljK/lh7rvvIkiCmVjaG8gIiIKZWNobyAiICDimqAg6YeN6ZaL5qmf5b6MIHN3dHBtIOeUsSBzeXN0ZW1kIOiHquWLleWVn+WLle+8jOeEoemcgOaJi+WLleaTjeS9nCIKZWNobyAiICDimqAg5Yu/5Z+36KGMIHN3dHBtX3NldHVwIC0tb3ZlcndyaXRl77yM5pyD5bCO6Ie05YWs6ZGw5pS56K6KIgplY2hvICI9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0iCg==";

function _decodeTpmScript(b64) {
  // UTF-8 decode from base64 (supports Chinese/multibyte)
  try {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new TextDecoder("utf-8").decode(bytes);
  } catch (_) {
    return "# decode error — please download from server\n";
  }
}

const TPM_FULL_SETUP_SCRIPT = _decodeTpmScript(_TPM_FULL_SETUP_B64);

const TPM_BUNDLE_README = `TPM 設定包 — HiBA-AB / Form System Kit Composer
=====================================================

包含檔案：
  01_tpm_full_setup.sh    — 完整 TPM 初始化（首次安裝用）
  get-machine-pubkey.sh   — 公鑰匯出（之後重新取得公鑰用）

使用步驟：
  1. 將此資料夾上傳至目標 Linux / Raspberry Pi 伺服器

  2. 執行完整初始化（首次安裝，需 root）：
       sudo bash 01_tpm_full_setup.sh
     → 自動安裝 swtpm、建立持久化金鑰
     → 執行完成後同目錄產生 machine-pubkey.pem

  3. 將 machine-pubkey.pem 上傳至 Kit Composer 平台

注意：
  - 重複執行 01_tpm_full_setup.sh 是安全的（冪等設計，不會重建金鑰）
  - 若只需重新取得公鑰，執行 get-machine-pubkey.sh（不需 sudo）
  - 重開機後 swtpm 由 systemd 自動啟動，無需手動操作
`;

// ── TPM 公鑰腳本（內嵌，無伺服器時也能下載） ──────────────────────────────────
const GET_MACHINE_PUBKEY_SCRIPT = `#!/bin/sh
# get-machine-pubkey.sh — Form System Kit Composer
# 匯出 TPM RSA-2048 簽名公鑰（handle 0x81000001）至 machine-pubkey.pem
# 前置條件：請先執行 sudo bash 01_tpm_full_setup.sh
set -eu

HANDLE="0x81000001"
FIXED_PATH="/var/lib/swtpm-hiba/signing_public.pem"

# 優先讀取 01_tpm_full_setup.sh 預建的公鑰
if [ -f "$FIXED_PATH" ]; then
  cp "$FIXED_PATH" machine-pubkey.pem
  echo ""
  echo "  Source   : $FIXED_PATH"
  echo "  Saved to : $(pwd)/machine-pubkey.pem"
  echo ""
  echo "  請將 machine-pubkey.pem 上傳至 Form System Kit Composer 平台。"
  echo ""
  exit 0
fi

# 備選：從 TPM handle 直接匯出
if command -v tpm2_readpublic > /dev/null 2>&1; then
  if tpm2_readpublic --object-context "$HANDLE" --output machine-pubkey.pem --format pem 2>/dev/null; then
    if grep -q "BEGIN PUBLIC KEY" machine-pubkey.pem 2>/dev/null; then
      echo ""
      echo "  Source   : TPM handle $HANDLE"
      echo "  Saved to : $(pwd)/machine-pubkey.pem"
      echo ""
      echo "  請將 machine-pubkey.pem 上傳至 Form System Kit Composer 平台。"
      echo ""
      exit 0
    fi
  fi
fi

echo "" >&2
echo "Error: TPM public key not found." >&2
echo "  Please run first: sudo bash 01_tpm_full_setup.sh" >&2
echo "" >&2
exit 1
`;

// ── Kit 資料 ──────────────────────────────────────────────────────────────
const PLATFORM_FRONTEND_HIDDEN_KIT_IDS = new Set(["mod-subscription-kit"]);
const PLATFORM_FRONTEND_HIDDEN_FLOW_IDS = new Set(["subscription"]);

const fallbackKits = [
  kit("platform-core-kit", "平台核心", "foundation", true, "提供應用程式 shell、設定、資料庫連線、健康檢查、語系與 API 呼叫基礎。", []),
  kit("tenant-auth-kit", "租戶與登入權限", "security", true, "管理租戶、登入、API key、使用者角色與資料隔離邊界。含 RegisterPage（登入/登出/密碼修改）與 ManagerPage（管理者用戶 CRUD，role=manager 限定）。", ["platform-core-kit"]),
  kit("station-data-link-kit", "站點資料串聯", "data-model", true, "保存並標準化站點資料，將 lot、winder、product_id 串成可追溯資料鏈。", ["platform-core-kit", "tenant-auth-kit"]),
  kit("upload-validation-kit", "檔案上傳與驗證", "workflow", false, "上傳 CSV、Excel 或 PDF，建立工作、驗證內容、顯示錯誤並允許修正。", ["platform-core-kit", "tenant-auth-kit"], [], ["import-pipeline-kit"]),
  kit("import-pipeline-kit", "資料匯入流程", "workflow", false, "將已驗證檔案轉成匯入工作，提交到正式資料表。", ["platform-core-kit", "tenant-auth-kit", "station-data-link-kit"]),
  kit("query-traceability-kit", "查詢與追溯", "business", false, "依 lot、product_id 與動態欄位查詢跨站點追溯資料。", ["platform-core-kit", "tenant-auth-kit", "station-data-link-kit"]),
  kit("analytics-kit", "分析與報表", "analytics", false, "提供分析儀表板、artifact 瀏覽、即時分析與圖表摘要。", ["platform-core-kit", "tenant-auth-kit", "station-data-link-kit", "query-traceability-kit"]),
  kit("station-admin-kit", "站點與規則管理", "admin", false, "管理泛用站點、欄位 schema、驗證規則、分析欄位對應與站點連結。", ["platform-core-kit", "tenant-auth-kit", "station-data-link-kit"]),
  kit("generic-forms-kit", "通用表格管理", "admin", false, "動態定義表格欄位 schema、上傳 CSV 資料、瀏覽與刪除記錄；無需修改程式碼即可新增自訂表格。含 FormsPage 三 subtab UI（Schema 編輯／CSV 上傳／記錄瀏覽）。", ["platform-core-kit", "tenant-auth-kit"]),
  kit("audit-edit-kit", "稽核與資料修正", "governance", false, "資料修正時保留原因、前後差異與操作稽核紀錄。", ["platform-core-kit", "tenant-auth-kit", "station-data-link-kit"]),
  kit("logs-ops-kit", "日誌與維運", "operations", false, "查看、搜尋、統計、清理與下載系統日誌。", ["platform-core-kit", "tenant-auth-kit"]),
];

const categoryMeta = {
  foundation: { label: "平台基礎", group: "平台基礎" },
  security: { label: "權限安全", group: "平台基礎" },
  "data-model": { label: "資料模型", group: "資料核心" },
  workflow: { label: "流程作業", group: "資料核心" },
  business: { label: "業務查詢", group: "業務功能" },
  analytics: { label: "分析報表", group: "業務功能" },
  admin: { label: "管理設定", group: "治理管理" },
  governance: { label: "稽核治理", group: "治理管理" },
  operations: { label: "系統維運", group: "維運" },
  integration: { label: "外部串接", group: "串接服務" },
};

// ── 業務流程定義 ────────────────────────────────────────────────────────────
const flows = [
  {
    id: "data-import",
    name: "資料匯入",
    description: "上傳 CSV、Excel 或 PDF，驗證內容後匯入正式資料表",
    kits: ["upload-validation-kit", "import-pipeline-kit"],
    subflows: [
      { id: "pdf-convert", name: "PDF → CSV", description: "自動將 PDF 轉換為 CSV 再進行驗證匯入" },
    ],
    pages: ["上傳頁", "匯入工作頁", "錯誤檢視頁"],
  },
  {
    id: "query-trace",
    name: "查詢追溯",
    description: "依 lot、product_id 與動態欄位跨站點查詢與追溯資料",
    kits: ["station-data-link-kit", "query-traceability-kit"],
    subflows: [],
    pages: ["查詢頁", "追溯結果頁"],
  },
  {
    id: "analytics",
    name: "資料分析",
    description: "儀表板、圖表摘要與異常偵測分析",
    kits: ["analytics-kit"],
    requiresFlows: ["query-trace"],
    subflows: [],
    pages: ["分析儀表板", "報表頁"],
  },
  {
    id: "generic-forms",
    name: "通用表格管理",
    description: "動態定義表格 schema、上傳 CSV、瀏覽記錄；管理者可在不修改程式碼的情況下新增自訂表格",
    kits: ["generic-forms-kit"],
    subflows: [],
    pages: ["通用表格頁（Schema 編輯 / CSV 上傳 / 記錄瀏覽）"],
  },
  {
    id: "governance",
    name: "管理治理",
    description: "站點與規則管理、稽核紀錄與系統維運日誌",
    kits: ["station-admin-kit", "audit-edit-kit", "logs-ops-kit"],
    subflows: [
      { id: "audit", name: "稽核與資料修正", description: "保留修改原因與前後差異，完整稽核軌跡" },
      { id: "ops-logs", name: "日誌與維運", description: "查看、搜尋、統計與下載系統日誌" },
    ],
    pages: ["站點管理頁", "稽核頁", "日誌頁"],
  },
];


const typeLabels = { text: "文字", integer: "整數", decimal: "小數", date: "日期" };

// ── 狀態 ────────────────────────────────────────────────────────────────────
const state = {
  kits: fallbackKits,
  selected: new Set(),
  selectedFlows: new Set(),
  selectedSubflows: new Map(),
  selectedSubfeatures: new Map(),
  subfeatureOptions: new Map(),
  activePreviewKit: "",
  manifestSource: "fallback",
  searchQuery: "",
  uploadedTables: [],
  tableSchema: new Map(),
  activeSchemaTable: null,
  nodeOrder: [],
  nodeRelations: new Map(),
  nodeConfirmed: false,
  tableData: new Map(),
  pkFkSuggestions: null,
  pkFkApplied: null,
  fkHighlights: new Set(),
  machinePubkey: '',
  deploymentMode: 'online',
};

const elements = {};

start();

// ── 啟動 ────────────────────────────────────────────────────────────────────
async function start() {
  cacheElements();
  state.kits = await loadKitCatalog();
  document.querySelector("#manifest-warning").hidden = state.manifestSource !== "fallback";
  resetToRequiredKits();
  bindNavigation();
  bindDatabaseInputs();
  bindToolbarActions();
  bindSearch();
  bindFlows();
  bindCsvUpload();
  bindNodeEditor();
  bindDeploymentMode();
  renderAll();
  await initMachineGate();
}

function cacheElements() {
  [
    "flow-grid",
    "kit-grid",
    "kit-count",
    "kit-search",
    "selection-summary",
    "dependency-list",
    "preview-tabs",
    "preview-body",
    "generation-summary",
    "package-file-list",
    "assembly-command-list",
    "recipe-output",
    "uploaded-tables-list",
    "node-editor-summary",

  ].forEach((id) => {
    elements[toCamel(id)] = document.querySelector(`#${id}`);
  });
}

function toCamel(value) {
  return value.replace(/-([a-z])/g, (_, char) => char.toUpperCase());
}

function escapeHtml(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// All caller sites must pass only HTML built exclusively from escapeHtml()-wrapped
// user values and hardcoded structural strings — no raw user data allowed at the sink.
function sanitizeHtml(html) { return html; }

function kit(id, name, category, required, capability, dependencies, subfeatures = [], optionalDependencies = []) {
  return { id, name, category, required, capability, dependencies, subfeatures, optionalDependencies };
}

// ── Kit Manifest 載入 ────────────────────────────────────────────────────────
async function loadKitCatalog() {
  try {
    const response = await fetch("../kits/form-analysis.kit-manifest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`Manifest load failed: ${response.status}`);
    const manifest = await response.json();
    state.manifestSource = "manifest";
    return normalizeManifestKits(manifest.kits || []).filter(isPlatformFrontendKit);
  } catch {
    state.manifestSource = "fallback";
    return fallbackKits.filter(isPlatformFrontendKit);
  }
}

function normalizeManifestKits(manifestKits) {
  return manifestKits.map((item) =>
    kit(
      item.id,
      item.displayName || item.id,
      item.category || "foundation",
      Boolean(item.required),
      item.businessCapability || item.capability || "",
      item.dependencies || [],
      normalizeManifestSubfeatures(item.id, item.subfeatures || []),
      item.optionalDependencies || [],
    ),
  );
}

function isPlatformFrontendKit(item) {
  return item && !PLATFORM_FRONTEND_HIDDEN_KIT_IDS.has(item.id);
}

function normalizeManifestSubfeatures(parentId, subfeatures) {
  return subfeatures.map((item) => ({
    id: item.id,
    parentId,
    name: item.displayName || item.id,
    description: item.businessCapability || "此功能由 manifest 宣告。",
    dependencies: item.dependencies || [],
    aliases: item.aliases || [],
    externalServices: item.externalServices || [],
    options: item.options || [],
    entitlement: item.entitlement || null,
  }));
}

function resetToRequiredKits() {
  state.selected.clear();
  state.selectedSubfeatures.clear();
  state.subfeatureOptions.clear();
  state.kits.filter((item) => item.required).forEach((item) => addKitWithDependencies(item.id));
  state.activePreviewKit = selectedKits()[0]?.id || "";
}

// ── Navigation ───────────────────────────────────────────────────────────────
function bindNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("is-active"));
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("is-visible"));
      button.classList.add("is-active");
      const view = document.querySelector(`#view-${button.dataset.view}`);
      if (!view) return;
      view.classList.add("is-visible");

    });
  });
}

function bindDatabaseInputs() {
  ["usage-scale", "data-criticality", "analytics-need", "deployment-mode"].forEach((id) => {
    document.querySelector(`#${id}`).addEventListener("change", renderAll);
  });
}

function bindToolbarActions() {
  document.querySelector("#clear-optional").addEventListener("click", () => {
    resetToRequiredKits();
    renderAll();
  });
  document.querySelector("#clear-flows").addEventListener("click", () => {
    state.selectedFlows.clear();
    state.selectedSubflows.clear();
    applyFlowSelection();
    renderAll();
  });
  document.querySelector("#copy-generation-command")?.addEventListener("click", copyGenerationCommand);
  document.querySelector("#copy-recipe-json")?.addEventListener("click", copyRecipeJson);
  document.querySelector("#download-recipe-json")?.addEventListener("click", downloadRecipeJson);
  document.querySelector("#download-package")?.addEventListener("click", downloadPackage);

  document.querySelector("#package-machine-pubkey-file")?.addEventListener("change", (event) => {
    handleMachinePubkeyFile(event.target.files?.[0], {
      statusEl: document.querySelector("#package-pem-status"),
      showGate: false,
    });
  });

}

// ── TPM 公鑰綁定關卡 ────────────────────────────────────────────────────────
async function initMachineGate() {
  const overlay = document.getElementById("machine-gate-overlay");
  if (!overlay) return;

  document.getElementById("gate-bypass-btn")?.addEventListener("click", () => { overlay.setAttribute("hidden", ""); });
  document.getElementById("gate-proceed-btn")?.addEventListener("click", () => { overlay.setAttribute("hidden", ""); });

  // Attach listeners unconditionally — both buttons are present in "register"
  // and "already-registered" (dimmed) states; the early-return below must not
  // prevent these from being wired up.
  document.getElementById("gate-machine-pubkey-file")?.addEventListener("change", (e) => {
    handleMachinePubkeyFile(e.target.files?.[0], {
      statusEl: document.getElementById("gate-status"),
      // serverRunning is not yet determined here; handleMachinePubkeyFile will
      // try the API and fall back gracefully if the server is unavailable.
      serverRunning: true,
      showGate: true,
    });
  });

  document.getElementById("gate-download-script")?.addEventListener("click", async () => {
    function _dlBlob(content, filename, mime) {
      const blob = content instanceof Blob ? content : new Blob([content], { type: mime || "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    }
    try {
      if (typeof JSZip !== "undefined") {
        const zip = new JSZip();
        zip.file("01_tpm_full_setup.sh", TPM_FULL_SETUP_SCRIPT);
        zip.file("get-machine-pubkey.sh", GET_MACHINE_PUBKEY_SCRIPT);
        zip.file("README.txt", TPM_BUNDLE_README);
        const blob = await zip.generateAsync({ type: "blob" });
        _dlBlob(blob, "tpm-setup-bundle.zip", "application/zip");
      } else {
        _dlBlob(TPM_FULL_SETUP_SCRIPT, "01_tpm_full_setup.sh");
        _dlBlob(GET_MACHINE_PUBKEY_SCRIPT, "get-machine-pubkey.sh");
      }
    } catch (err) {
      console.error("TPM bundle download failed:", err);
      _dlBlob(TPM_FULL_SETUP_SCRIPT, "01_tpm_full_setup.sh");
      _dlBlob(GET_MACHINE_PUBKEY_SCRIPT, "get-machine-pubkey.sh");
    }
  });

  let serverRunning = false;
  let machines = [];
  try {
    const resp = await fetch("/api/machines");
    if (resp.ok) { machines = await resp.json(); serverRunning = true; }
  } catch (_) { /* server not running */ }

  if (serverRunning && Array.isArray(machines) && machines.length > 0 && machines[0].pubkey) {
    state.machinePubkey = machines[0].pubkey;
    overlay.removeAttribute("hidden");
    _showGateRegistered(machines);
    return;
  }

  overlay.removeAttribute("hidden");
  if (!serverRunning) {
    document.getElementById("gate-offline-notice")?.removeAttribute("hidden");
  }

}

async function handleMachinePubkeyFile(file, { statusEl, serverRunning = true, showGate = false } = {}) {
  if (!file) return;
  const pem = (await file.text()).trim();
  const isPem = pem.includes("-----BEGIN PUBLIC KEY-----") && pem.includes("-----END PUBLIC KEY-----");
  if (!isPem) {
    if (statusEl) {
      statusEl.style.color = "var(--red,#dc2626)";
      statusEl.textContent = "找不到有效 PEM 公鑰";
    }
    return;
  }

  if (statusEl) {
    statusEl.style.color = "var(--ink-3,#6b7280)";
    statusEl.textContent = "驗證中…";
  }

  if (!serverRunning) {
    state.machinePubkey = pem;
    if (showGate) _showGateRegistered([{ pubkey: pem, registeredAt: new Date().toISOString() }]);
    if (statusEl) {
      statusEl.style.color = "var(--success,#16a34a)";
      statusEl.textContent = "✓ PEM 格式有效（離線模式）";
    }
    return;
  }

  try {
    const resp = await fetch("/api/register-machine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pubkey: pem }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      if (statusEl) {
        statusEl.style.color = "var(--red,#dc2626)";
        statusEl.textContent = `驗證失敗：${data.error || "invalid PEM"}`;
      }
      return;
    }
    state.machinePubkey = pem;
    if (showGate) {
      const refreshed = await fetch("/api/machines").then((r) => r.json()).catch(() => [{ pubkey: pem, registeredAt: new Date().toISOString() }]);
      _showGateRegistered(refreshed);
    }
    if (statusEl) {
      statusEl.style.color = "var(--success,#16a34a)";
      statusEl.textContent = "✓ PEM 已驗證並登錄";
    }
  } catch (_) {
    state.machinePubkey = pem;
    if (statusEl) {
      statusEl.style.color = "var(--success,#16a34a)";
      statusEl.textContent = "✓ PEM 格式有效（未連接伺服器）";
    }
  }
}

function _showGateRegistered(machines) {
  const registeredArea = document.getElementById("gate-registered-area");
  const listEl = document.getElementById("gate-machine-list");
  const stepsEl = document.getElementById("gate-register-steps");
  if (stepsEl) stepsEl.style.opacity = "0.45";
  if (registeredArea) registeredArea.removeAttribute("hidden");
  if (listEl) {
    listEl.innerHTML = machines.map((m) => {
      // Show PEM header + key fingerprint preview
      const lines = (m.pubkey || "").split("\n").filter(Boolean);
      const b64 = lines.filter(l => !l.startsWith("-----")).join("");
      const preview = b64.length > 20 ? b64.slice(0, 12) + "…" + b64.slice(-8) : (m.pubkey || "").slice(0, 20);
      return `<div>RSA-2048 公鑰 <code>${preview}</code>&nbsp;&nbsp;<span style="color:var(--ink-4,#8293a8);font-family:sans-serif;">${new Date(m.registeredAt).toLocaleDateString("zh-TW")}</span></div>`;
    }).join("");
  }
  const statusEl = document.getElementById("gate-status");
  if (statusEl) { statusEl.style.color = "var(--success,#16a34a)"; statusEl.textContent = "✓ TPM 公鑰已登錄"; }
}

function bindSearch() {
  elements.kitSearch.addEventListener("input", (event) => {
    state.searchQuery = event.target.value.trim().toLowerCase();
    renderKits();
  });
}

// ── Flows ────────────────────────────────────────────────────────────────────
function bindFlows() {
  elements.flowGrid.addEventListener("click", (event) => {
    const toggleBtn = event.target.closest("[data-flow-toggle]");
    if (toggleBtn && !toggleBtn.disabled) {
      const flowId = toggleBtn.dataset.flowToggle;
      state.selectedFlows.has(flowId) ? state.selectedFlows.delete(flowId) : state.selectedFlows.add(flowId);
      applyFlowSelection();
      renderAll();
    }
  });
  elements.flowGrid.addEventListener("change", (event) => {
    const key = event.target.dataset.subflowToggle;
    if (!key) return;
    const [flowId, subflowId] = key.split("::");
    const set = state.selectedSubflows.get(flowId) || new Set();
    event.target.checked ? set.add(subflowId) : set.delete(subflowId);
    state.selectedSubflows.set(flowId, set);
    applyFlowSelection();
    renderAll();
  });
}

function applyFlowSelection() {
  resetToRequiredKits();
  const allFlows = new Set(state.selectedFlows);
  allFlows.forEach((flowId) => {
    const flow = visibleFlows().find((f) => f.id === flowId);
    flow?.requiresFlows?.forEach((reqId) => allFlows.add(reqId));
  });
  allFlows.forEach((flowId) => {
    const flow = visibleFlows().find((f) => f.id === flowId);
    if (!flow) return;
    flow.kits.forEach(addKitWithDependencies);
  });
  keepActivePreviewSelected();
}

function isAutoRequiredFlow(flowId) {
  return flows.some((f) => state.selectedFlows.has(f.id) && f.requiresFlows?.includes(flowId));
}

function renderFlows() {
  if (!elements.flowGrid) return;
  elements.flowGrid.innerHTML = visibleFlows().map(flowCardTemplate).join("");
}

function visibleFlows() {
  return flows.filter((flow) =>
    !PLATFORM_FRONTEND_HIDDEN_FLOW_IDS.has(flow.id) &&
    flow.kits.every((kitId) => !PLATFORM_FRONTEND_HIDDEN_KIT_IDS.has(kitId))
  );
}

function flowCardTemplate(flow) {
  const isSelected = state.selectedFlows.has(flow.id);
  const isAuto = isAutoRequiredFlow(flow.id);
  const isOn = isSelected || isAuto;
  const selectedSubflowsForFlow = state.selectedSubflows.get(flow.id) || new Set();
  const subflowsHtml = isOn && flow.subflows?.length ? `
    <div class="flow-subflows">
      <p class="flow-subflows-label">選配功能</p>
      ${flow.subflows.map((sf) => `
        <label class="flow-subflow-item">
          <input type="checkbox" data-subflow-toggle="${escapeHtml(flow.id)}::${escapeHtml(sf.id)}"
            ${selectedSubflowsForFlow.has(sf.id) ? "checked" : ""} />
          <span>
            <strong>${escapeHtml(sf.name)}</strong>
            <em>${escapeHtml(sf.description)}</em>
          </span>
        </label>
      `).join("")}
    </div>
  ` : "";
  const kitListHtml = flow.kits.map((kitId) => {
    const k = findKit(kitId);
    return k ? `<div class="flow-kit-item"><strong>${escapeHtml(k.name)}</strong><span class="kit-id">${escapeHtml(k.id)}</span></div>` : "";
  }).join("");
  return `
    <article class="flow-card ${isOn ? "is-selected" : ""}">
      <div class="flow-card-head">
        <div class="flow-card-info">
          <h4>${escapeHtml(flow.name)}</h4>
          <p class="flow-desc">${escapeHtml(flow.description)}</p>
          <div class="flow-pages">${flow.pages.map((p) => `<span class="flow-page-tag">${escapeHtml(p)}</span>`).join("")}</div>
        </div>
        <button class="flow-toggle-btn ${isOn ? "is-on" : ""}"
          data-flow-toggle="${escapeHtml(flow.id)}"
          ${isAuto ? "disabled" : ""}
          type="button">${isAuto ? "必須" : isSelected ? "✓ 已選" : "+ 加入"}</button>
      </div>
      ${subflowsHtml}
      <details class="flow-kit-details">
        <summary>包含元件（${flow.kits.length} 個 kit）</summary>
        <div class="flow-kit-list">${kitListHtml}</div>
      </details>
    </article>
  `;
}

// ── CSV 上傳 ──────────────────────────────────────────────────────────────────
function bindCsvUpload() {
  const zone = document.querySelector("#csv-upload-zone");
  const fileInput = document.querySelector("#csv-file-input");
  const browseBtn = document.querySelector("#csv-browse-btn");

  browseBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => handleCsvFiles(Array.from(fileInput.files)));

  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("is-dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("is-dragover");
    const files = Array.from(e.dataTransfer.files).filter((f) => /\.(csv|tsv)$/i.test(f.name));
    if (files.length) handleCsvFiles(files);
  });

  if (elements.uploadedTablesList) {
    elements.uploadedTablesList.addEventListener("click", (e) => {
      const removeBtn = e.target.closest("[data-remove-table]");
      if (removeBtn) {
        const tableId = removeBtn.dataset.removeTable;
        state.uploadedTables = state.uploadedTables.filter((t) => t.id !== tableId);
        state.tableSchema.delete(tableId);
        state.nodeOrder = state.nodeOrder.filter((id) => id !== tableId);
        state.nodeRelations.delete(tableId);
        state.nodeRelations.forEach((rel, key) => { if (rel.childTableId === tableId) state.nodeRelations.delete(key); });
        state.tableData.delete(tableId);
        state.pkFkSuggestions = null;
        if (state.activeSchemaTable === tableId) state.activeSchemaTable = state.uploadedTables[0]?.id || null;
        if (!state.uploadedTables.length) { const btn = document.querySelector("#open-node-editor"); if (btn) btn.disabled = true; }
        renderUploadedTables();
        renderNodeEditorSummary();
        renderGeneration();
      }
      const tabBtn = e.target.closest("[data-schema-select]");
      if (tabBtn) {
        state.activeSchemaTable = tabBtn.dataset.schemaSelect;
        renderUploadedTables();
      }
    });
  }
}

function handleCsvFiles(files) {
  files.forEach((file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const { headers, rows } = parseCsv(e.target.result);
      if (!headers.length) return;
      const tableId = `tbl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const tableName = file.name.replace(/\.(csv|tsv)$/i, "");
      const sampleRows = rows.slice(0, 20);
      const columns = headers.map((name, i) => ({
        name,
        displayName: name,
        type: inferColumnType(sampleRows.map((row) => row[i])),
        required: false,
        isPK: i === 0,
        fkTarget: "",
      }));
      state.uploadedTables.push({ id: tableId, filename: file.name, tableName, columns });
      state.tableSchema.set(tableId, columns);
      state.tableData.set(tableId, rows);
      state.pkFkSuggestions = null;
      if (!state.activeSchemaTable) state.activeSchemaTable = tableId;
      renderUploadedTables();
      renderNodeEditorSummary();
      renderGeneration();
      const btn = document.querySelector("#open-node-editor");
      if (btn) btn.disabled = false;
    };
    reader.readAsText(file);
  });
}

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (!lines.length) return { headers: [], rows: [] };
  const parseRow = (line) => {
    const result = [];
    let field = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"' && line[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') inQuotes = false;
        else field += ch;
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === "," || ch === "\t") {
        result.push(field.trim()); field = "";
      } else {
        field += ch;
      }
    }
    result.push(field.trim());
    return result;
  };
  const headers = parseRow(lines[0]);
  const rows = lines.slice(1).map(parseRow); // all rows for FK/PK analysis
  return { headers, rows };
}

function inferColumnType(samples) {
  const nonEmpty = samples.filter((s) => s && s.trim());
  if (!nonEmpty.length) return "text";
  if (nonEmpty.every((s) => /^\d{4}-\d{2}-\d{2}/.test(s))) return "date";
  if (nonEmpty.every((s) => /^\d+$/.test(s.trim()))) return "integer";
  if (nonEmpty.every((s) => /^\d+\.?\d*$/.test(s.trim()))) return "decimal";
  return "text";
}

function renderUploadedTables() {
  if (!elements.uploadedTablesList) return;
  if (!state.uploadedTables.length) {
    elements.uploadedTablesList.innerHTML = "";
    return;
  }
  const tableItems = state.uploadedTables.map((t) => `
    <div class="uploaded-table-item ${t.id === state.activeSchemaTable ? "is-active" : ""}" data-schema-select="${escapeHtml(t.id)}">
      <span class="uploaded-table-name">${escapeHtml(t.tableName)}</span>
      <span class="uploaded-table-meta">${t.columns.length} 欄 · ${(state.tableData.get(t.id) || []).length} 列</span>
      <button class="uploaded-table-remove" data-remove-table="${escapeHtml(t.id)}" type="button" title="移除">✕</button>
    </div>
  `).join("");

  const sug = state.pkFkSuggestions;
  const applied = state.pkFkApplied;
  const bannerHtml = sug
    ? `<div class="pk-fk-banner">
        <div class="pk-fk-banner-result">
          偵測到 <strong>${sug.pks.length}</strong> 個 PK 建議、<strong>${sug.fks.length}</strong> 個 FK 建議
          ${sug.pks.length + sug.fks.length === 0 ? "（無符合規則的欄位）" : ""}
        </div>
        ${sug.pks.map((p) => `<div class="pk-fk-tag pk-tag">🔑 ${escapeHtml(p.tableName)}.${escapeHtml(p.colName)} <span>${escapeHtml(p.confidence)}</span></div>`).join("")}
        ${sug.fks.map((f) => `<div class="pk-fk-tag fk-tag">🔗 ${escapeHtml(f.tableName)}.${escapeHtml(f.colName)} → ${escapeHtml(f.targetTableName)}.${escapeHtml(f.targetColName)} <span>${escapeHtml(f.confidence)}</span></div>`).join("")}
        ${sug.pks.length + sug.fks.length > 0
          ? `<button class="ghost-action pk-fk-apply-btn" id="pk-fk-apply" type="button">套用建議到 Schema</button>`
          : ""}
      </div>`
    : applied
    ? `<div class="pk-fk-detect-bar pk-fk-applied">
        <span>✓ 已套用 ${applied.pkCount} 個 PK、${applied.fkCount} 個 FK 到 Schema 與欄位關係編輯器</span>
      </div>`
    : "";

  elements.uploadedTablesList.innerHTML = sanitizeHtml(tableItems + bannerHtml);

  document.querySelector("#pk-fk-apply")?.addEventListener("click", () => {
    const sug = state.pkFkSuggestions;
    applyPkFkSuggestions(sug);
    state.pkFkApplied = { pkCount: sug.pks.length, fkCount: sug.fks.length };
    state.pkFkSuggestions = null;
    renderUploadedTables();
    renderNodeEditorSummary();
    renderGeneration();
    // 3 秒後清除成功提示
    setTimeout(() => { state.pkFkApplied = null; renderUploadedTables(); }, 3000);
  });
}

function findForeignKeys() {
  if (!state.uploadedTables.length) return;
  const sug = detectPkFk();
  applyPkFkSuggestions(sug);
  state.fkHighlights = new Set(sug.fks.map((f) => `${f.tableId}::${f.colName}`));
  state.pkFkApplied = { pkCount: sug.pks.length, fkCount: sug.fks.length };
  state.pkFkSuggestions = null;
  renderUploadedTables();
  renderNodeEditorSummary();
  renderGeneration();
  openNodeEditor();
}

// ── PK / FK 評分輔助函式 ──────────────────────────────────────────────────────

// 訊號 1 — 名稱啟發（弱訊號，跨語言常見慣例）
// 分數高低影響門檻，不單獨決定是否為 PK
function pkNameScore(name) {
  if (/^(id|uid|uuid|pk|row_id|record_id)$/i.test(name)) return 3;
  if (/_id$/i.test(name)) return 2;
  if (/_no$|_code$|_key$|_sn$|_seq$|^no$|^code$|^key$/i.test(name)) return 1;
  if (/號$/.test(name)) return 1; // 中文：批號、卡號、料號、工號…
  return 0;
}

// 訊號 2 — 唯一性（強訊號，資料 ≥3 筆時才有意義）
function pkUniquenessScore(nonEmpty, totalRows) {
  if (totalRows < 3 || !nonEmpty.length) return 0;
  const ratio = new Set(nonEmpty).size / nonEmpty.length;
  if (ratio === 1) return 4;
  if (ratio >= 0.95) return 2;
  return 0;
}

// 訊號 3 — 值型態（中訊號，與命名語言無關）
// 偵測：UUID / 字母前綴碼 / 長數字識別碼 / 等差序列
function pkValuePatternScore(vals) {
  if (!vals.length) return 0;
  if (vals.every((v) => /^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v))) return 2;
  if (vals.every((v) => /^[A-Za-z]{1,6}[-_][A-Z0-9][-A-Z0-9]*$/i.test(v))) return 2;
  if (vals.every((v) => /^\d{6,}$/.test(v))) return 2; // 6位以上純數字（批號、卡號等編碼）
  if (vals.length >= 3 && vals.every((v) => /^\d+$/.test(v))) {
    const nums = vals.map(Number);
    const step = nums[1] - nums[0];
    if (step > 0 && nums.every((n, i) => i === 0 || n - nums[i - 1] === step)) return 2;
  }
  return 0;
}

// ── PK / FK 自動偵測（評分制） ────────────────────────────────────────────────
// 三訊號加總：名稱(0-3) + 唯一性(0-4) + 值型態(0-2)
// 門檻：名稱或值型態至少一個有貢獻，且總分 ≥3 才列為候選
// 資料不足時（<3筆）唯一性訊號為 0，依賴名稱+值型態判斷
function detectPkFk() {
  const pks = [];
  const fks = [];

  state.uploadedTables.forEach((table) => {
    const rows = state.tableData.get(table.id) || [];
    const schema = state.tableSchema.get(table.id) || [];
    schema.forEach((col, colIdx) => {
      const allVals = rows.map((r) => (r[colIdx] ?? "").trim());
      const nonEmpty = allVals.filter(Boolean);
      const ns = pkNameScore(col.name);
      const us = pkUniquenessScore(nonEmpty, allVals.length);
      const vs = pkValuePatternScore(nonEmpty.slice(0, 50));
      const total = ns + us + vs;
      if ((ns < 1 && vs < 2) || total < 3) return; // 無明確訊號則略過
      pks.push({
        tableId: table.id, tableName: table.tableName, colName: col.name,
        confidence: total >= 6 ? "high" : "medium",
        _score: total,
      });
    });
  });

  const pkColsByTable = new Map();
  pks.forEach(({ tableId, colName }) => {
    if (!pkColsByTable.has(tableId)) pkColsByTable.set(tableId, new Set());
    pkColsByTable.get(tableId).add(colName);
  });

  state.uploadedTables.forEach((tableA) => {
    const schemaA = state.tableSchema.get(tableA.id) || [];
    const rowsA = state.tableData.get(tableA.id) || [];
    state.uploadedTables.forEach((tableB) => {
      if (tableA.id === tableB.id) return;
      const schemaB = state.tableSchema.get(tableB.id) || [];
      const rowsB = state.tableData.get(tableB.id) || [];
      const pkColsB = pkColsByTable.get(tableB.id) || new Set();
      schemaA.forEach((colA, colAIdx) => {
        schemaB.forEach((colB, colBIdx) => {
          // B 的欄位是 PK 候選：已偵測到，或有強命名訊號(≥2)
          const bIsPkCandidate = colB.isPK || pkColsB.has(colB.name) || pkNameScore(colB.name) >= 2;
          if (!bIsPkCandidate) return;
          const aN = colA.name.toLowerCase();
          const bN = colB.name.toLowerCase();
          const tBN = tableB.tableName.toLowerCase();
          const nameMatch =
            aN === `${tBN}_${bN}` ||
            aN === `${tBN}_id` ||
            aN === `${tBN}_no` ||
            aN === bN; // 同名跨表（語言無關）
          if (!nameMatch) return;
          let confidence = "medium";
          if (rowsA.length && rowsB.length) {
            const valsA = new Set(rowsA.map((r) => (r[colAIdx] ?? "").trim()).filter(Boolean));
            const valsB = new Set(rowsB.map((r) => (r[colBIdx] ?? "").trim()).filter(Boolean));
            if (valsA.size && valsB.size) {
              let overlap = 0;
              valsA.forEach((v) => { if (valsB.has(v)) overlap++; });
              confidence = overlap / valsA.size >= 0.5 ? "high" : "medium";
            }
          }
          fks.push({ tableId: tableA.id, tableName: tableA.tableName, colName: colA.name, targetTableId: tableB.id, targetTableName: tableB.tableName, targetColName: colB.name, confidence });
        });
      });
    });
  });

  return { pks, fks };
}

function applyPkFkSuggestions({ pks, fks }) {
  // 更新 schema 欄位標記
  pks.forEach(({ tableId, colName }) => {
    const schema = state.tableSchema.get(tableId);
    if (!schema) return;
    schema.forEach((col) => { col.isPK = col.name === colName; });
  });
  fks.forEach(({ tableId, colName, targetTableId, targetColName }) => {
    const schema = state.tableSchema.get(tableId);
    const col = schema?.find((c) => c.name === colName);
    if (col) col.fkTarget = `${targetTableId}::${targetColName}`;
  });

  // 同步欄位關係編輯器：以 FK 自動建立 parent→child 關係
  if (!state.nodeOrder.length) state.nodeOrder = state.uploadedTables.map((t) => t.id);
  fks.forEach(({ tableId, colName, targetTableId, targetColName }) => {
    // tableId 持有 FK 指向 targetTableId → targetTableId 為父，tableId 為子
    if (state.nodeRelations.has(targetTableId)) return; // 已有關係，不覆蓋
    const alreadyChild = Array.from(state.nodeRelations.values()).some((r) => r.childTableId === tableId);
    if (alreadyChild) return;
    state.nodeRelations.set(targetTableId, { childTableId: tableId, parentCol: targetColName, childCol: colName });
    state.nodeOrder = state.nodeOrder.filter((id) => id !== tableId);
  });
}

// ── 欄位關係編輯器 (node editor) ─────────────────────────────────────────────
function renderNodeEditorSummary() {
  const el = elements.nodeEditorSummary;
  if (!el) return;
  const openBtn = document.querySelector("#open-node-editor");
  const findBtn = document.querySelector("#find-fk");
  if (!state.uploadedTables.length) {
    el.innerHTML = `<div class="empty-state">上傳 CSV 後開啟欄位關係編輯器</div>`;
    if (openBtn) openBtn.disabled = true;
    if (findBtn) findBtn.disabled = true;
    return;
  }
  if (openBtn) openBtn.disabled = false;
  if (findBtn) findBtn.disabled = false;
  const order = state.nodeOrder.length ? state.nodeOrder : state.uploadedTables.map((t) => t.id);
  const chips = order.map((id, i) => {
    const t = state.uploadedTables.find((x) => x.id === id);
    if (!t) return "";
    const rel = state.nodeRelations.get(id);
    const childName = rel ? (state.uploadedTables.find((x) => x.id === rel.childTableId)?.tableName || "") : "";
    return `
      <span class="node-summary-chip">
        <strong>Step ${i + 1}</strong>${escapeHtml(t.tableName)}${childName ? ` ↓${escapeHtml(childName)}` : ""}
      </span>
      ${i < order.length - 1 ? '<span class="node-summary-arrow">→</span>' : ""}
    `;
  }).join("");
  el.innerHTML = `<div class="node-summary-flow">${chips}</div>`;
}

function bindDeploymentMode() {
  document.querySelectorAll("input[name='deploy-mode']").forEach((radio) => {
    radio.addEventListener("change", () => {
      state.deploymentMode = radio.value;
      const hint = document.getElementById("offline-prepare-hint");
      if (hint) hint.hidden = state.deploymentMode !== "offline";
    });
  });
}

function bindNodeEditor() {
  document.querySelector("#find-fk")?.addEventListener("click", findForeignKeys);
  document.querySelector("#open-node-editor")?.addEventListener("click", openNodeEditor);
  document.querySelector("#node-editor-close")?.addEventListener("click", closeNodeEditor);
  document.querySelector("#node-editor-cancel")?.addEventListener("click", closeNodeEditor);
  document.querySelector("#node-editor-confirm")?.addEventListener("click", confirmNodeEditor);
}

function openNodeEditor() {
  if (!state.uploadedTables.length) return;
  if (!state.nodeOrder.length) state.nodeOrder = state.uploadedTables.map((t) => t.id);
  const overlay = document.querySelector("#node-editor-overlay");
  overlay.hidden = false;
  renderNodeCanvas();
}

function closeNodeEditor() {
  document.querySelector("#node-editor-overlay").hidden = true;
}

function confirmNodeEditor() {
  state.nodeConfirmed = true;
  const statusEl = document.querySelector("#node-editor-status");
  if (statusEl) statusEl.textContent = "✓ 已確認設定";
  closeNodeEditor();
  renderNodeEditorSummary();
  renderGeneration();
}

function renderNodeCanvas() {
  const canvas = document.querySelector("#node-canvas");
  if (!canvas) return;
  const order = state.nodeOrder;
  const rowHtml = order.map((tableId, i) => {
    const t = state.uploadedTables.find((x) => x.id === tableId);
    if (!t) return "";
    const schema = state.tableSchema.get(tableId) || [];
    const rel = state.nodeRelations.get(tableId);
    const connector = i < order.length - 1
      ? `<div class="node-connector">→<span>Step ${i + 1}→${i + 2}</span></div>`
      : "";
    const colsHtml = schema.map((col) => {
      const isFk = state.fkHighlights.has(`${tableId}::${col.name}`) || Boolean(col.fkTarget);
      return `<div class="node-col-item ${isFk ? "is-fk" : ""}"><span class="col-type">${col.type[0].toUpperCase()}</span><span class="node-col-name">${escapeHtml(col.displayName || col.name)}</span>${isFk ? '<span class="fk-badge">FK</span>' : ""}</div>`;
    }).join("");
    const childBtnClass = rel ? "node-child-btn has-child" : "node-child-btn";
    const childBtnLabel = rel ? `↓ 子表格：${escapeHtml(state.uploadedTables.find((x) => x.id === rel.childTableId)?.tableName || "")}` : "↓ 設定子表格";
    const childConfigHtml = rel ? buildChildConfigHtml(tableId, rel) : "";
    return `
      <div class="node-col-wrap" style="display:flex;flex-direction:column;align-items:center">
        <div class="node-card" draggable="true" data-node-id="${escapeHtml(tableId)}">
          <div class="node-card-head">
            <span class="node-step-badge">Step ${i + 1}</span>
            <span class="node-table-name" title="${escapeHtml(t.tableName)}">${escapeHtml(t.tableName)}</span>
            <span class="node-drag-handle" title="拖曳排序">⠿</span>
          </div>
          <div class="node-card-body">
            <div class="node-col-list">${colsHtml}</div>
            <button class="${childBtnClass}" data-child-toggle="${escapeHtml(tableId)}" type="button">${childBtnLabel}</button>
          </div>
        </div>
        ${rel ? `<div class="node-child-area"><div class="node-down-arrow"></div>${childConfigHtml}</div>` : ""}
      </div>
      ${connector}
    `;
  }).join("");
  canvas.innerHTML = sanitizeHtml(`<div class="node-row">${rowHtml}</div>`);
  bindNodeCardDrag(canvas);
  canvas.querySelectorAll("[data-child-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => toggleChildConfig(btn.dataset.childToggle));
  });
  canvas.querySelectorAll("[data-child-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const parentId = btn.dataset.childRemove;
      const rel = state.nodeRelations.get(parentId);
      if (rel?.childTableId && !state.nodeOrder.includes(rel.childTableId)) {
        state.nodeOrder.push(rel.childTableId);
      }
      state.nodeRelations.delete(parentId);
      renderNodeCanvas();
    });
  });
  canvas.querySelectorAll("[data-child-select]").forEach((sel) => {
    sel.addEventListener("change", () => onChildTableSelect(sel.dataset.childSelect, sel.value));
  });
  canvas.querySelectorAll("[data-child-parent-col]").forEach((sel) => {
    sel.addEventListener("change", () => {
      const rel = state.nodeRelations.get(sel.dataset.childParentCol);
      if (rel) { rel.parentCol = sel.value; }
    });
  });
  canvas.querySelectorAll("[data-child-col]").forEach((sel) => {
    sel.addEventListener("change", () => {
      const rel = state.nodeRelations.get(sel.dataset.childCol);
      if (rel) { rel.childCol = sel.value; }
    });
  });
}

function buildChildConfigHtml(parentTableId, rel) {
  const parentTable = state.uploadedTables.find((t) => t.id === parentTableId);
  const childTable = state.uploadedTables.find((t) => t.id === rel.childTableId);
  const parentSchema = state.tableSchema.get(parentTableId) || [];
  const childSchema = state.tableSchema.get(rel.childTableId) || [];
  const colOptions = (cols, selected) => cols.map((c) =>
    `<option value="${escapeHtml(c.name)}" ${selected === c.name ? "selected" : ""}>${escapeHtml(c.displayName || c.name)}</option>`
  ).join("");
  // only tables not already used as children elsewhere (and not the parent itself)
  const childCandidates = state.uploadedTables.filter((t) => {
    if (t.id === parentTableId) return false;
    // allow if it's already the current child, or not a child of anyone
    if (t.id === rel.childTableId) return true;
    return !Array.from(state.nodeRelations.values()).some((r) => r.childTableId === t.id);
  });
  const childTableOptions = childCandidates.map((t) =>
    `<option value="${escapeHtml(t.id)}" ${t.id === rel.childTableId ? "selected" : ""}>${escapeHtml(t.tableName)}</option>`
  ).join("");
  return `
    <div class="node-child-config">
      <div class="node-child-config-head">
        <strong>↓ 子表格關聯</strong>
        <button class="node-child-remove" data-child-remove="${escapeHtml(parentTableId)}" type="button" title="移除子表格">✕</button>
      </div>
      <div class="node-child-relation-label">
        <span class="relation-table-name">${escapeHtml(parentTable?.tableName || "")}</span>
        <span class="relation-arrow">串接</span>
        <select class="relation-table-select" data-child-select="${escapeHtml(parentTableId)}">
          ${childTableOptions}
        </select>
      </div>
      <div class="node-child-key-row">
        <div class="key-group">
          <span class="lbl">${escapeHtml(parentTable?.tableName || "父表")} 欄位</span>
          <select data-child-parent-col="${escapeHtml(parentTableId)}">
            <option value="">— 選欄位 —</option>${colOptions(parentSchema, rel.parentCol)}
          </select>
        </div>
        <span class="key-eq">=</span>
        <div class="key-group">
          <span class="lbl">${escapeHtml(childTable?.tableName || "子表")} 欄位</span>
          <select data-child-col="${escapeHtml(parentTableId)}">
            <option value="">— 選欄位 —</option>${colOptions(childSchema, rel.childCol)}
          </select>
        </div>
      </div>
    </div>
  `;
}

function toggleChildConfig(parentTableId) {
  if (state.nodeRelations.has(parentTableId)) {
    const rel = state.nodeRelations.get(parentTableId);
    // add the former child back into the node flow
    if (rel.childTableId && !state.nodeOrder.includes(rel.childTableId)) {
      state.nodeOrder.push(rel.childTableId);
    }
    state.nodeRelations.delete(parentTableId);
    renderNodeCanvas();
    return;
  }
  // pick first table not already a child of something and not the parent itself
  const usedAsChild = new Set(Array.from(state.nodeRelations.values()).map((r) => r.childTableId));
  const candidate = state.uploadedTables.find((t) => t.id !== parentTableId && !usedAsChild.has(t.id));
  if (!candidate) return;
  // remove the chosen child from the main node flow
  state.nodeOrder = state.nodeOrder.filter((id) => id !== candidate.id);
  state.nodeRelations.set(parentTableId, { childTableId: candidate.id, parentCol: "", childCol: "" });
  renderNodeCanvas();
}

function onChildTableSelect(parentTableId, newChildTableId) {
  const rel = state.nodeRelations.get(parentTableId);
  if (!rel) return;
  const oldChildTableId = rel.childTableId;
  if (oldChildTableId === newChildTableId) return;
  // restore old child to node flow
  if (oldChildTableId && !state.nodeOrder.includes(oldChildTableId)) {
    state.nodeOrder.push(oldChildTableId);
  }
  // remove new child from node flow
  state.nodeOrder = state.nodeOrder.filter((id) => id !== newChildTableId);
  rel.childTableId = newChildTableId;
  rel.parentCol = "";
  rel.childCol = "";
  renderNodeCanvas();
}

let dragSrcId = null;

function bindNodeCardDrag(canvas) {
  canvas.querySelectorAll(".node-card[draggable]").forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      dragSrcId = card.dataset.nodeId;
      card.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    card.addEventListener("dragend", () => card.classList.remove("is-dragging"));
    card.addEventListener("dragover", (e) => { e.preventDefault(); card.classList.add("is-dragover"); });
    card.addEventListener("dragleave", () => card.classList.remove("is-dragover"));
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("is-dragover");
      const dropId = card.dataset.nodeId;
      if (!dragSrcId || dragSrcId === dropId) return;
      const order = state.nodeOrder;
      const srcIdx = order.indexOf(dragSrcId);
      const dstIdx = order.indexOf(dropId);
      if (srcIdx === -1 || dstIdx === -1) return;
      order.splice(srcIdx, 1);
      order.splice(dstIdx, 0, dragSrcId);
      renderNodeCanvas();
    });
  });
}

// ── Kit Catalog ───────────────────────────────────────────────────────────────
function renderKits() {
  const kits = filteredKits();
  elements.kitGrid.innerHTML = kits.length ? kits.map(kitCardTemplate).join("") : `<div class="empty-state">沒有符合搜尋條件的 kit</div>`;
  document.querySelectorAll("[data-kit-toggle]").forEach((input) => input.addEventListener("change", onKitToggle));
  document.querySelectorAll("[data-kit-row]").forEach((row) => row.addEventListener("click", onKitRowClick));
  document.querySelectorAll("[data-subfeature-toggle]").forEach((input) => input.addEventListener("change", onSubfeatureToggle));
  document.querySelectorAll("[data-subfeature-option]").forEach((input) => input.addEventListener("change", onSubfeatureOption));
  document.querySelectorAll("[data-enable-all-subfeatures]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      enableAllSubfeatures(button.dataset.enableAllSubfeatures);
      renderAll();
    });
  });
}

function filteredKits() {
  if (!state.searchQuery) return state.kits;
  return state.kits.filter((item) => {
    const haystack = [item.id, item.name, item.capability, ...subfeatureList(item).flatMap((sub) => [sub.id, sub.name, sub.description])].join(" ").toLowerCase();
    return haystack.includes(state.searchQuery);
  });
}

function kitCardTemplate(item) {
  const checked = state.selected.has(item.id) ? "checked" : "";
  const disabled = item.required ? "disabled" : "";
  const expanded = state.searchQuery ? "" : "hidden";
  return `
    <article class="kit-card" data-category="${escapeHtml(item.category)}" data-kit-row="${escapeHtml(item.id)}" tabindex="0">
      <div class="kit-top">
        <div>
          <h4>${escapeHtml(item.name)}</h4>
          <p class="kit-id">${escapeHtml(item.id)}</p>
        </div>
        <input class="kit-checkbox" type="checkbox" data-kit-toggle="${escapeHtml(item.id)}" ${checked} ${disabled} aria-label="${escapeHtml(item.name)}" />
      </div>
      <p class="kit-desc">${escapeHtml(item.capability)}</p>
      <div class="tag-row">${kitTagsTemplate(item)}</div>
      <div class="kit-subfeatures" id="kit-subfeatures-${escapeHtml(item.id)}" ${expanded}>${subfeaturesTemplate(item)}</div>
    </article>
  `;
}

function kitTagsTemplate(item) {
  const meta = categoryMeta[item.category] || { label: item.category, group: "未分類" };
  const tags = [
    `<span class="tag tag-cat">${escapeHtml(meta.group)}</span>`,
    `<span class="tag tag-kind">${escapeHtml(meta.label)}</span>`,
    ...item.dependencies.map((id) => `<span class="tag">依賴 ${escapeHtml(id)}</span>`),
  ];
  if (item.required) tags.push(`<span class="tag tag-req">必選</span>`);
  return tags.join("");
}

function subfeaturesTemplate(item) {
  const locked = item.required;
  const action = locked
    ? `<span class="locked-note">必選 kit 的子功能會自動納入。</span>`
    : `<button class="ghost-action subfeature-action-button" data-enable-all-subfeatures="${escapeHtml(item.id)}" type="button">全選子功能</button>`;
  return `
    <div class="subfeature-actions">${action}</div>
    <div class="subfeature-grid">${subfeatureList(item).map((subfeature) => subfeatureTemplate(subfeature, locked)).join("")}</div>
  `;
}

function subfeatureList(item) {
  return item?.subfeatures || [];
}

function subfeatureTemplate(subfeature, locked) {
  const key = subfeatureKey(subfeature.parentId, subfeature.id);
  const checked = locked || state.selectedSubfeatures.get(subfeature.parentId)?.has(subfeature.id) ? "checked" : "";
  const disabled = locked ? "disabled" : "";
  const entitlement = subfeature.entitlement ? `<span class="subfeature-service-note">需要方案權益</span>` : "";
  return `
    <div class="subfeature-item">
      <div>
        <strong>${escapeHtml(subfeature.name)}</strong>
        <span>${escapeHtml(subfeature.description)}</span>
        ${entitlement}
        ${subfeatureOptionsTemplate(subfeature, locked)}
      </div>
      <input class="kit-checkbox" type="checkbox" data-subfeature-toggle="${escapeHtml(key)}" ${checked} ${disabled} aria-label="${escapeHtml(subfeature.name)}" />
    </div>
  `;
}

function subfeatureOptionsTemplate(subfeature, locked) {
  if (!subfeature.options?.length) return "";
  return `<div class="subfeature-options">${subfeature.options.map((option) => subfeatureOptionTemplate(subfeature, option, locked)).join("")}</div>`;
}

function subfeatureOptionTemplate(subfeature, option, locked) {
  const key = subfeatureKey(subfeature.parentId, subfeature.id);
  const value = subfeatureOptionValue(subfeature, option);
  const disabled = locked ? "disabled" : "";
  if (option.type === "boolean") {
    const checked = value === true || value === "true" ? "checked" : "";
    return `<label class="subfeature-option-toggle"><input type="checkbox" data-subfeature-option="${escapeHtml(key)}" data-option-id="${escapeHtml(option.id)}" ${checked} ${disabled} />${escapeHtml(option.displayName)}</label>`;
  }
  const choices = (option.choices || []).map((choice) => `<option value="${escapeHtml(choice.value)}" ${String(choice.value) === String(value) ? "selected" : ""}>${escapeHtml(choice.displayName)}</option>`).join("");
  return `<label class="subfeature-option"><span>${escapeHtml(option.displayName)}</span><select data-subfeature-option="${escapeHtml(key)}" data-option-id="${escapeHtml(option.id)}" ${disabled}>${choices}</select></label>`;
}

function onKitToggle(event) {
  const id = event.target.dataset.kitToggle;
  event.target.checked ? addKitWithDependencies(id) : removeOptionalKit(id);
  keepActivePreviewSelected();
  renderAll();
}

function onKitRowClick(event) {
  if (event.target.closest("input, button, select, summary")) return;
  const row = event.currentTarget;
  const detail = document.querySelector(`#kit-subfeatures-${row.dataset.kitRow}`);
  detail.hidden = !detail.hidden;
}

function onSubfeatureToggle(event) {
  const { kitId, subfeatureId } = parseSubfeatureKey(event.target.dataset.subfeatureToggle);
  const selected = state.selectedSubfeatures.get(kitId) || new Set();
  event.target.checked ? selected.add(subfeatureId) : selected.delete(subfeatureId);
  state.selectedSubfeatures.set(kitId, selected);
  renderAll();
}

function onSubfeatureOption(event) {
  const { kitId, subfeatureId } = parseSubfeatureKey(event.target.dataset.subfeatureOption);
  const values = state.subfeatureOptions.get(subfeatureKey(kitId, subfeatureId)) || {};
  values[event.target.dataset.optionId] = event.target.type === "checkbox" ? event.target.checked : event.target.value;
  state.subfeatureOptions.set(subfeatureKey(kitId, subfeatureId), values);
  renderPreview();
  renderGeneration();
}

function addKitWithDependencies(id) {
  if (PLATFORM_FRONTEND_HIDDEN_KIT_IDS.has(id)) return;
  const item = findKit(id);
  if (!item) return;
  item.dependencies.forEach(addKitWithDependencies);
  state.selected.add(id);
  enableDefaultSubfeatures(id);
}

function removeOptionalKit(id) {
  const item = findKit(id);
  if (!item || item.required) return;
  state.selected.delete(id);
  state.selectedSubfeatures.delete(id);
  Array.from(state.subfeatureOptions.keys()).filter((key) => key.startsWith(`${id}::`)).forEach((key) => state.subfeatureOptions.delete(key));
  state.kits.forEach((candidate) => {
    if (candidate.required || !state.selected.has(candidate.id)) return;
    const isHardDependent = candidate.dependencies.includes(id);
    const isOptionalCompanion = item.optionalDependencies.includes(candidate.id);
    if (isHardDependent || isOptionalCompanion) removeOptionalKit(candidate.id);
  });
}

function enableDefaultSubfeatures(kitId) {
  if (!state.selectedSubfeatures.has(kitId)) enableAllSubfeatures(kitId);
}

function enableAllSubfeatures(kitId) {
  const item = findKit(kitId);
  const ids = new Set(subfeatureList(item).map((subfeature) => subfeature.id));
  state.selectedSubfeatures.set(kitId, ids);
  subfeatureList(item).forEach((subfeature) => {
    if (!subfeature.options?.length) return;
    const key = subfeatureKey(kitId, subfeature.id);
    const values = state.subfeatureOptions.get(key) || {};
    subfeature.options.forEach((option) => {
      if (!Object.prototype.hasOwnProperty.call(values, option.id)) values[option.id] = option.defaultValue;
    });
    state.subfeatureOptions.set(key, values);
  });
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderAll() {
  renderFlows();
  renderKits();
  renderSummary();
  renderDatabaseLayout();
  renderNodeEditorSummary();
  renderDatabaseRecommendation();
  renderPreview();
  renderGeneration();
}

function renderDatabaseLayout() {
  const ready = ["usage-scale", "data-criticality", "analytics-need", "deployment-mode"]
    .every((id) => document.querySelector(`#${id}`)?.value);
  document.querySelector("#database-layout")?.classList.toggle("is-ready", ready);
}

function renderSummary() {
  const items = selectedKits();
  elements.kitCount.textContent = `${items.length} kits selected`;
  if (elements.selectionSummary) elements.selectionSummary.innerHTML = items.map(summaryTemplate).join("");
  if (elements.dependencyList) elements.dependencyList.innerHTML = items.map(dependencyTemplate).join("");
}

function summaryTemplate(item) {
  const selectedCount = selectedSubfeatures(item).length;
  const totalCount = subfeatureList(item).length;
  return `<div class="summary-item"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.capability)}</span><small>${selectedCount}/${totalCount} 子功能</small></div>`;
}

function dependencyTemplate(item) {
  const deps = item.dependencies.length ? item.dependencies.map((id) => escapeHtml(findKit(id)?.name || id)).join("、") : "無";
  const paid = selectedSubfeatures(item).filter((subfeature) => subfeature.entitlement).length;
  return `<div class="dependency-item"><strong>${escapeHtml(item.id)}</strong><span>依賴：${deps}</span><span>${paid ? `付費 gating：${paid} 項` : "無 gating"}</span></div>`;
}

function computeDbEngine() {
  const score = scoreByValue("usage-scale", { single: 0, team: 2, company: 3 }) +
    scoreByValue("data-criticality", { demo: 0, ops: 2, critical: 3 }) +
    scoreByValue("analytics-need", { low: 0, medium: 1, high: 2 }) +
    scoreByValue("deployment-mode", { local: 0, intranet: 1, cloud: 2 });
  return { engine: score >= 4 ? "postgresql" : "sqlite", score };
}

function renderDatabaseRecommendation() {
  const { engine, score } = computeDbEngine();
  const displayName = engine === "postgresql" ? "PostgreSQL" : "SQLite";
  document.querySelector("#db-engine").textContent = displayName;
  document.querySelector("#db-reason").textContent = engine === "postgresql"
    ? "建議使用 PostgreSQL 作為正式資料庫。這套系統會保存匯入紀錄、批號追溯、使用者權限與背景處理結果，需要可長期保存、備份、多人同時使用的資料庫。"
    : "如果只是本機展示、單人測試或可重建資料，可先使用 SQLite 快速啟動；正式使用前再切換到 PostgreSQL。";
  document.querySelector("#db-meter-fill").style.width = `${Math.min(100, 40 + score * 8)}%`;
}

function scoreByValue(id, weights) {
  return weights[document.querySelector(`#${id}`).value] ?? 0;
}

function renderPreview() {
  if (!elements.previewBody) return;
  const items = selectedKits();
  if (!items.length) {
    if (elements.previewTabs) elements.previewTabs.innerHTML = "";
    elements.previewBody.innerHTML = `<div class="empty-state">尚未選擇業務流程</div>`;
    return;
  }
  if (!items.some((item) => item.id === state.activePreviewKit)) state.activePreviewKit = items[0].id;
  if (elements.previewTabs) {
    elements.previewTabs.innerHTML = items.map((item) => `
      <button class="preview-tab ${item.id === state.activePreviewKit ? "is-active" : ""}" data-preview-kit="${item.id}">${item.name}</button>
    `).join("");
    document.querySelectorAll("[data-preview-kit]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activePreviewKit = button.dataset.previewKit;
        renderPreview();
      });
    });
  }
  const item = findKit(state.activePreviewKit) || items[0];
  elements.previewBody.innerHTML = previewTemplate(item);
}

function previewTemplate(item) {
  const mockFn = kitMockups[item.id];
  const mockHtml = mockFn ? mockFn(item) : defaultMockup(item);
  return `<div class="preview-kit-mock">${mockHtml}</div>`;
}

function defaultMockup(item) {
  const subs = selectedSubfeatures(item);
  return `
    <h3>${escapeHtml(item.name)}</h3>
    <p class="kit-hint">${escapeHtml(item.capability)}</p>
    <div class="preview-grid">
      ${subs.map((s) => `<div class="preview-card"><strong>${escapeHtml(s.name)}</strong><span>${escapeHtml(s.description)}</span></div>`).join("") || `<div class="preview-card"><strong>底層能力</strong><span>此 kit 提供後端或基礎設施能力，無獨立頁面。</span></div>`}
    </div>
  `;
}

function pvHeader(name, category, desc) {
  return `<div class="pv-header">
    <div class="pv-header-text"><h3>${name}</h3><p>${desc}</p></div>
    <span class="pv-category-badge">${category}</span>
  </div>`;
}
function pvSection(label, html) {
  return `<div class="pv-section"><span class="pv-label">${label}</span>${html}</div>`;
}

const kitMockups = {
  "platform-core-kit": () =>
    pvHeader("平台核心", "基礎設施", "FastAPI 啟動、SQLAlchemy session、健康檢查端點，無獨立頁面。") +
    pvSection("驗證方式建議", `<div class="preview-gif-fallback">
      <p>此 kit 無獨立 UI 頁面，建議以下方式展示：</p>
      <ul>
        <li>錄製 <code>GET /healthz</code> 回傳 <code>{"status":"ok"}</code> 的 GIF</li>
        <li>截圖顯示 DB migration 成功 log</li>
      </ul>
    </div>`),

  "tenant-auth-kit": () =>
    pvHeader("租戶與登入權限", "安全", "多租戶登入、API key 管理與使用者角色。") +
    pvSection("登入頁面", `<div class="mock-login">
      <h4>登入系統</h4>
      <div class="mock-input-row"><label>租戶 ID</label><div class="mock-input">tenant-alpha</div></div>
      <div class="mock-input-row"><label>API Key</label><div class="mock-input">fsk-••••••••••••</div></div>
      <div class="mock-btn">登入</div>
    </div>`) +
    pvSection("使用者管理", `<table class="mock-table">
      <thead><tr><th>使用者</th><th>角色</th><th>狀態</th></tr></thead>
      <tbody>
        <tr><td>admin@co</td><td>管理員</td><td><span class="mock-status-badge ok">啟用</span></td></tr>
        <tr><td>user01@co</td><td>一般</td><td><span class="mock-status-badge ok">啟用</span></td></tr>
      </tbody>
    </table>`),

  "station-data-link-kit": () =>
    pvHeader("站點資料串聯", "資料模型", "P1 → P2 → P3 製程資料鏈，依 lot 追溯。") +
    pvSection("站點串聯結構", `<div class="mock-data-chain">
      <div class="mock-chain-node">P1<br><small style="font-weight:400;color:#444">捲繞</small></div>
      <span class="mock-chain-arrow">→</span>
      <div class="mock-chain-node">P2<br><small style="font-weight:400;color:#444">成型</small></div>
      <span class="mock-chain-arrow">→</span>
      <div class="mock-chain-node">P3<br><small style="font-weight:400;color:#444">測試</small></div>
    </div>`) +
    pvSection("資料範例", `<table class="mock-table mock-schema-table">
      <thead><tr><th>lot_no</th><th>winder</th><th>product_id</th><th>站點</th></tr></thead>
      <tbody>
        <tr><td>LOT-001</td><td>W1</td><td>P-20240101-001</td><td>P1</td></tr>
        <tr><td>LOT-001</td><td>W1</td><td>P-20240101-001</td><td>P2</td></tr>
      </tbody>
    </table>`),

  "upload-validation-kit": () =>
    pvHeader("檔案上傳與驗證", "流程", "拖曳上傳 CSV/PDF，即時驗證並顯示錯誤摘要。") +
    pvSection("上傳區", `<div class="mock-upload-zone">📂 拖曳 CSV / PDF 至此，或點擊選擇檔案</div>`) +
    pvSection("檔案清單 &amp; 狀態", `<div class="mock-file-list">
      <div class="mock-file-item"><span>P1_data_20240115.csv</span><span class="mock-status-badge ok">✓ 驗證通過 (320 列)</span></div>
      <div class="mock-file-item"><span>P2_data_20240115.csv</span><span class="mock-status-badge error">✕ 3 列錯誤</span></div>
      <div class="mock-file-item"><span>form_report.pdf</span><span class="mock-status-badge pending">⟳ 轉換中</span></div>
    </div>`) +
    pvSection("錯誤摘要", `<table class="mock-table">
      <thead><tr><th>列號</th><th>欄位</th><th>錯誤原因</th></tr></thead>
      <tbody>
        <tr><td>Row 12</td><td>tensile</td><td>數值超出範圍（6.8 > 6.0）</td></tr>
        <tr><td>Row 47</td><td>lot_no</td><td>格式不符（應為 LOT-）</td></tr>
      </tbody>
    </table>`),

  "import-pipeline-kit": () =>
    pvHeader("資料匯入流程", "流程", "Parse → Validate → Commit 三階段匯入至正式資料表。") +
    pvSection("匯入工作進度", `<div class="mock-job-steps">
      <div class="mock-job-step">建立 Job</div>
      <div class="mock-job-step active">▶ 驗證中</div>
      <div class="mock-job-step">Commit</div>
      <div class="mock-job-step">完成</div>
    </div>`) +
    pvSection("工作清單", `<table class="mock-table">
      <thead><tr><th>Job ID</th><th>資料表</th><th>列數</th><th>錯誤</th><th>狀態</th></tr></thead>
      <tbody>
        <tr><td>JOB-042</td><td>P1</td><td>320</td><td>0</td><td><span class="mock-status-badge ok">已提交</span></td></tr>
        <tr><td>JOB-043</td><td>P2</td><td>288</td><td>3</td><td><span class="mock-status-badge error">待修正</span></td></tr>
      </tbody>
    </table>`),

  "query-traceability-kit": () =>
    pvHeader("查詢與追溯", "業務", "依 lot、product_id 查詢跨站點資料並顯示追溯鏈。") +
    pvSection("查詢條件", `<div class="mock-query-form">
      <label>Lot No<div class="mock-input">LOT-001</div></label>
      <label>日期範圍<div class="mock-input">2024-01 ~ 2024-03</div></label>
      <div class="mock-btn">查詢</div>
    </div>`) +
    pvSection("查詢結果", `<table class="mock-table">
      <thead><tr><th>lot_no</th><th>winder</th><th>P1</th><th>P2</th><th>P3</th></tr></thead>
      <tbody>
        <tr><td>LOT-001</td><td>W1</td><td>✓</td><td>✓</td><td>✓</td></tr>
        <tr><td>LOT-002</td><td>W2</td><td>✓</td><td>⚠ 警告</td><td>—</td></tr>
      </tbody>
    </table>`) +
    pvSection("追溯鏈", `<div class="mock-data-chain" style="flex-wrap:wrap;gap:6px">
      <div class="mock-chain-node" style="font-size:12px">P1 · LOT-001</div>
      <span class="mock-chain-arrow">→</span>
      <div class="mock-chain-node" style="font-size:12px">P2 · LOT-001</div>
      <span class="mock-chain-arrow">→</span>
      <div class="mock-chain-node" style="font-size:12px">P3 · LOT-001</div>
    </div>`),

  "analytics-kit": () =>
    pvHeader("分析與報表", "分析", "KPI 儀表板、圖表摘要與即時分析。") +
    pvSection("KPI 摘要", `<div class="pv-grid-3">
      <div class="mock-kpi-card"><div class="kpi-val">1,284</div><div class="kpi-lbl">本月匯入列數</div></div>
      <div class="mock-kpi-card"><div class="kpi-val">98.2%</div><div class="kpi-lbl">驗證通過率</div></div>
      <div class="mock-kpi-card"><div class="kpi-val">3</div><div class="kpi-lbl">異常批次</div></div>
    </div>`) +
    pvSection("趨勢圖", `<div class="mock-chart-bars">
      <span style="height:60%;background:var(--teal)"></span>
      <span style="height:80%;background:var(--teal)"></span>
      <span style="height:45%;background:var(--teal)"></span>
      <span style="height:90%;background:var(--blue)"></span>
      <span style="height:70%;background:var(--teal)"></span>
      <span style="height:55%;background:var(--teal)"></span>
    </div>`),

  "station-admin-kit": () =>
    pvHeader("站點與規則管理", "管理", "設定站點 schema、欄位規則與驗證條件。") +
    pvSection("欄位 Schema 設定", `<table class="mock-table mock-schema-table">
      <thead><tr><th>欄位名稱</th><th>型別</th><th>必填</th><th>驗證規則</th></tr></thead>
      <tbody>
        <tr><td>lot_no</td><td>text</td><td>✓</td><td>正規: ^LOT-</td></tr>
        <tr><td>tensile</td><td>decimal</td><td>✓</td><td>範圍: 3.5 ~ 6.0</td></tr>
        <tr><td>winder</td><td>text</td><td></td><td>—</td></tr>
      </tbody>
    </table>`) +
    pvSection("站點連結", `<div class="mock-data-chain">
      <div class="mock-chain-node" style="font-size:12px">P1 (捲繞)</div>
      <span class="mock-chain-arrow">⟵ lot_no ⟶</span>
      <div class="mock-chain-node" style="font-size:12px">P2 (成型)</div>
    </div>`),

  "audit-edit-kit": () =>
    pvHeader("稽核與資料修正", "治理", "保留修改原因、前後差異與操作稽核紀錄。") +
    pvSection("最近稽核事件", `
      <div class="mock-audit-item"><span class="audit-time">2024-03-01 14:22</span><span class="audit-action">修改</span><span>tensile: 4.2 → 4.5（原因：量測重校）</span></div>
      <div class="mock-audit-item"><span class="audit-time">2024-03-01 11:05</span><span class="audit-action">匯入</span><span>P1 Job #042 提交 320 列</span></div>
      <div class="mock-audit-item"><span class="audit-time">2024-02-28 09:30</span><span class="audit-action">刪除</span><span>LOT-099 全部記錄（原因：重複批次）</span></div>
    `) +
    pvSection("修改前後比較", `<div class="pv-grid-2">
      <div style="padding:10px;border:1px solid #fee2e2;border-radius:6px;background:#fef2f2;font-size:12px"><strong style="color:#991b1b">修改前</strong><br>tensile = 4.2</div>
      <div style="padding:10px;border:1px solid #dcfce7;border-radius:6px;background:#f0fdf4;font-size:12px"><strong style="color:#166534">修改後</strong><br>tensile = 4.5</div>
    </div>`),

  "logs-ops-kit": () =>
    pvHeader("日誌與維運", "維運", "查看、搜尋、統計與下載系統日誌。") +
    pvSection("日誌統計", `<div class="pv-grid-3">
      <div class="mock-kpi-card"><div class="kpi-val" style="font-size:18px">2,401</div><div class="kpi-lbl">今日 INFO</div></div>
      <div class="mock-kpi-card"><div class="kpi-val" style="font-size:18px;color:var(--amber)">14</div><div class="kpi-lbl">WARN</div></div>
      <div class="mock-kpi-card"><div class="kpi-val" style="font-size:18px;color:var(--red)">2</div><div class="kpi-lbl">ERROR</div></div>
    </div>`) +
    pvSection("即時日誌", `<div class="mock-log-viewer">
      <div><span class="log-ok">INFO</span>  09:00:01 | app startup complete</div>
      <div><span class="log-ok">INFO</span>  09:01:14 | JOB-042 committed 320 rows</div>
      <div><span class="log-warn">WARN</span>  09:03:07 | 3 rows skipped in JOB-043</div>
      <div><span class="log-err">ERROR</span> 09:15:33 | PDF conversion timeout: pdf_089</div>
    </div>`),
};

function renderGeneration() {
  const recipe = buildRecipe();
  if (elements.generationSummary) elements.generationSummary.innerHTML = [
    ["流程", recipe.selectedFlows.join("、") || "（未選擇）"],
    ["Kit", recipe.enabledKits.join("、")],
    ["Database", recipe.database.engine],
    ["資料表", recipe.tableSchemas.length ? `${recipe.tableSchemas.length} 個（含欄位定義）` : "未上傳"],
  ].map(([title, body]) => `<div class="summary-item"><strong>${title}</strong><span>${body}</span></div>`).join("");
  const rn = recipeName();
  if (elements.packageFileList) elements.packageFileList.innerHTML = [
    [`assembly/${rn}.recipe.json`,        "recipe.json 的組裝輸入"],
    [`assembly/${rn}-resolved-plan.json`, "kit 依賴解析結果"],
    ["dist/generated-system",             "組裝後的系統目錄"],
    [`dist/client-deploy-${rn}.zip`,      "客戶部署套件（最終輸出）"],
  ].map(([item, desc]) => `<div class="dependency-item"><strong>${item}</strong><span>${desc}</span></div>`).join("");
  if (elements.assemblyCommandList) elements.assemblyCommandList.innerHTML = assemblyCommands().map((command) => `<div class="dependency-item"><code>${command}</code></div>`).join("");
  if (elements.recipeOutput) elements.recipeOutput.value = recipeJsonText();
}

// ── Recipe / 輸出 ─────────────────────────────────────────────────────────────
function recipeName() {
  const short = {
    "data-import": "import",
    "query-trace": "query",
    "analytics":   "analytics",
    "governance":  "admin",
  };
  const parts = Array.from(state.selectedFlows).map(f => short[f] || f);
  return parts.length ? "form-system-" + parts.join("-") : "form-system";
}

function buildRecipe() {
  const selected = selectedKits();
  const tableSchemas = state.uploadedTables.map((t) => ({
    tableName: t.tableName,
    columns: (state.tableSchema.get(t.id) || []).map((col) => ({
      name: col.name,
      displayName: col.displayName,
      type: col.type,
      required: col.required,
      isPK: col.isPK,
      fkTarget: col.fkTarget || null,
    })),
  }));
  return {
    recipeVersion: "0.2.0",
    name: recipeName(),
    sourceManifest: "kits/form-analysis.kit-manifest.json",
    selectedFlows: Array.from(state.selectedFlows),
    enabledKits: selected.map((item) => item.id),
    selectedSubfeatures: Object.fromEntries(selected.map((item) => [item.id, selectedSubfeatures(item).map((sub) => sub.id)])),
    selectedSubfeatureOptions: Object.fromEntries(state.subfeatureOptions.entries()),
    tableSchemas,
    featureFlags: {},
    database: {
      engine: computeDbEngine().engine,
      connectionOwner: "platform-core-kit",
      autoGenerateConnection: true,
    },
    deploymentMode: state.deploymentMode || "online",
    ...(state.machinePubkey ? { machinePublicKey: state.machinePubkey } : {}),
  };
}

function recipeJsonText() {
  return JSON.stringify(buildRecipe(), null, 2);
}

function assemblyCommands() {
  const n = recipeName();
  return [
    `powershell -ExecutionPolicy Bypass -File tools\\validate-recipe.ps1 -RecipePath assembly\\${n}.recipe.json`,
    `powershell -ExecutionPolicy Bypass -File tools\\resolve-recipe.ps1 -RecipePath assembly\\${n}.recipe.json -OutputPath assembly\\${n}-resolved-plan.json`,
    `powershell -ExecutionPolicy Bypass -File tools\\assemble-system.ps1 -ResolvedPlanPath assembly\\${n}-resolved-plan.json`,
    `powershell -ExecutionPolicy Bypass -File tools\\package-client-deploy.ps1 -RecipeName ${n}`,
    `# 完成後客戶部署套件位於：dist\\client-deploy-${n}.zip`,
  ];
}

async function writeToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.cssText = "position:fixed;opacity:0;top:0;left:0;width:1px;height:1px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand("copy");
    textarea.remove();
    return ok;
  }
}

async function copyGenerationCommand() {
  const ok = await writeToClipboard(assemblyCommands().join("\n"));
  if (ok) flashButton("#copy-generation-command", "已複製", "複製組裝指令");
}

async function copyRecipeJson() {
  const ok = await writeToClipboard(recipeJsonText());
  if (ok) flashButton("#copy-recipe-json", "已複製", "複製");
}

function flashButton(selector, active, idle) {
  const button = document.querySelector(selector);
  if (!button) return;
  button.textContent = active;
  setTimeout(() => { button.textContent = idle; }, 1200);
}

function downloadRecipeJson() {
  const recipe = buildRecipe();
  const blob = new Blob([recipeJsonText()], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${recipe.name}.recipe.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  recordOperation("download-recipe");
}

// ── 部署套件下載 ──────────────────────────────────────────────────────────────

function buildDeployPs1(recipe, dateStr) {
  const kits = recipe.enabledKits.join(", ");
  const name = recipe.name;
  const db = recipe.database.engine;
  const L = [
    `# ${"═".repeat(64)}`,
    `#  Form System Kit Composer — 組裝協調腳本（Windows / PowerShell）`,
    `#  Recipe : ${name}`,
    `#  產生於 : ${dateStr}`,
    `#  Kits   : ${kits}`,
    `#  DB     : ${db}`,
    `# ${"═".repeat(64)}`,
    `#`,
    `#  用法（在 form-system-kit-composer 專案根目錄執行）：`,
    `#    powershell -ExecutionPolicy Bypass -File deploy.ps1`,
    `#    powershell -ExecutionPolicy Bypass -File deploy.ps1 -StartFrom 3  # 從組裝階段重試`,
    `#`,
    `#  階段：  1=準備  2=解析  3=組裝  4=打包`,
    `#  參數：`,
    `#    -ComposerRoot  kit-composer 專案路徑（預設：當前目錄）`,
    `#    -StartFrom     從指定階段開始（預設 1）`,
    ``,
    `param(`,
    `    [string]$ComposerRoot = (Get-Location).Path,`,
    `    [int]$StartFrom = 1`,
    `)`,
    ``,
    `$ErrorActionPreference = "Stop"`,
    `$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path`,
    `$PhasesDir    = Join-Path $ScriptDir "phases"`,
    `$RecipeName   = "${name}"`,
    `$AssemblyDir  = Join-Path $ComposerRoot "assembly"`,
    `$ResolvedPath = Join-Path $AssemblyDir "$RecipeName-resolved-plan.json"`,
    ``,
    `Write-Host "Form System Kit Composer — 組裝協調腳本" -ForegroundColor Cyan`,
    `Write-Host "ComposerRoot : $ComposerRoot" -ForegroundColor Gray`,
    `Write-Host "Recipe       : $RecipeName" -ForegroundColor Gray`,
    `Write-Host "StartFrom    : $StartFrom" -ForegroundColor Gray`,
    `Write-Host ""`,
    ``,
    `if (-not (Test-Path (Join-Path $ComposerRoot "tools"))) {`,
    `    Write-Error "找不到 tools\\ 目錄。請確認 -ComposerRoot 指向 form-system-kit-composer 專案根目錄。"`,
    `    exit 1`,
    `}`,
    ``,
    `# ── 階段 1：準備 recipe`,
    `if ($StartFrom -le 1) {`,
    `    Write-Host ""`,
    `    Write-Host "── 階段 1：準備 recipe" -ForegroundColor Cyan`,
    `    & powershell -ExecutionPolicy Bypass -File (Join-Path $PhasesDir "01-prepare.ps1") \``,
    `        -ComposerRoot $ComposerRoot -ScriptDir $ScriptDir -RecipeName $RecipeName -AssemblyDir $AssemblyDir`,
    `    if ($LASTEXITCODE -ne 0) { throw "階段 1 失敗，重試：deploy.ps1 -StartFrom 1" }`,
    `}`,
    ``,
    `# ── 階段 2：解析依賴`,
    `if ($StartFrom -le 2) {`,
    `    Write-Host ""`,
    `    Write-Host "── 階段 2：解析依賴" -ForegroundColor Cyan`,
    `    & powershell -ExecutionPolicy Bypass -File (Join-Path $PhasesDir "02-resolve.ps1") \``,
    `        -ComposerRoot $ComposerRoot -AssemblyDir $AssemblyDir -RecipeName $RecipeName -ResolvedPath $ResolvedPath`,
    `    if ($LASTEXITCODE -ne 0) { throw "階段 2 失敗，重試：deploy.ps1 -StartFrom 2" }`,
    `}`,
    ``,
    `# ── 階段 3：組裝系統`,
    `if ($StartFrom -le 3) {`,
    `    Write-Host ""`,
    `    Write-Host "── 階段 3：組裝系統" -ForegroundColor Cyan`,
    `    & powershell -ExecutionPolicy Bypass -File (Join-Path $PhasesDir "03-assemble.ps1") \``,
    `        -ComposerRoot $ComposerRoot -ResolvedPath $ResolvedPath`,
    `    if ($LASTEXITCODE -ne 0) { throw "階段 3 失敗，重試：deploy.ps1 -StartFrom 3" }`,
    `}`,
    ``,
    `# ── 階段 4：打包 ZIP（永遠執行）`,
    `Write-Host ""`,
    `Write-Host "── 階段 4：打包 ZIP" -ForegroundColor Cyan`,
    `& powershell -ExecutionPolicy Bypass -File (Join-Path $PhasesDir "04-package.ps1") \``,
    `    -ComposerRoot $ComposerRoot -RecipeName $RecipeName`,
    `if ($LASTEXITCODE -ne 0) { throw "階段 4 失敗，重試：deploy.ps1 -StartFrom 4" }`,
    ``,
    `$ClientZip = Join-Path $ComposerRoot "dist\\client-deploy-$RecipeName.zip"`,
    `Write-Host ""`,
    `Write-Host "${"═".repeat(56)}" -ForegroundColor Green`,
    `Write-Host "  完成！Client deploy ZIP 已產生：" -ForegroundColor Green`,
    `Write-Host "  $ClientZip" -ForegroundColor Yellow`,
    `Write-Host ""`,
    `Write-Host "  將此 ZIP 傳給部署人員，解壓後執行：" -ForegroundColor Gray`,
    `Write-Host "    (Windows)  powershell -ExecutionPolicy Bypass -File deploy.ps1" -ForegroundColor Gray`,
    `Write-Host "    (Linux)    bash deploy.sh" -ForegroundColor Gray`,
    `Write-Host "${"═".repeat(56)}" -ForegroundColor Green`,
  ];
  return L.join("\r\n");
}

function buildDeployPhase1Ps1() {
  const L = [
    `# ${"═".repeat(56)}`,
    `#  階段 1：準備 recipe`,
    `#  複製 recipe.json 至 assembly\\ 目錄並驗證格式`,
    `# ${"═".repeat(56)}`,
    `param(`,
    `    [string]$ComposerRoot,`,
    `    [string]$ScriptDir,`,
    `    [string]$RecipeName,`,
    `    [string]$AssemblyDir`,
    `)`,
    `$ErrorActionPreference = "Stop"`,
    `if (-not (Test-Path $AssemblyDir)) { New-Item -ItemType Directory -Force $AssemblyDir | Out-Null }`,
    `$RecipeDest = Join-Path $AssemblyDir "$RecipeName.recipe.json"`,
    `Copy-Item (Join-Path $ScriptDir "recipe.json") $RecipeDest -Force`,
    `Write-Host "  ✓ recipe.json 複製至 $RecipeDest"`,
    `Write-Host "  驗證 recipe..."`,
    `& powershell -ExecutionPolicy Bypass -File (Join-Path $ComposerRoot "tools\\validate-recipe.ps1") \``,
    `    -RecipePath $RecipeDest`,
    `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`,
    `Write-Host "  ✓ 驗證通過"`,
  ];
  return L.join("\r\n");
}

function buildDeployPhase2Ps1() {
  const L = [
    `# ${"═".repeat(56)}`,
    `#  階段 2：解析 kit 依賴`,
    `# ${"═".repeat(56)}`,
    `param(`,
    `    [string]$ComposerRoot,`,
    `    [string]$AssemblyDir,`,
    `    [string]$RecipeName,`,
    `    [string]$ResolvedPath`,
    `)`,
    `$ErrorActionPreference = "Stop"`,
    `$RecipeDest = Join-Path $AssemblyDir "$RecipeName.recipe.json"`,
    `Write-Host "  解析 kit 依賴..."`,
    `& powershell -ExecutionPolicy Bypass -File (Join-Path $ComposerRoot "tools\\resolve-recipe.ps1") \``,
    `    -RecipePath $RecipeDest -OutputPath $ResolvedPath`,
    `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`,
    `Write-Host "  ✓ 依賴解析完成：$ResolvedPath"`,
  ];
  return L.join("\r\n");
}

function buildDeployPhase3Ps1() {
  const L = [
    `# ${"═".repeat(56)}`,
    `#  階段 3：組裝系統`,
    `#  最耗時步驟，失敗後可用 -StartFrom 3 重試`,
    `# ${"═".repeat(56)}`,
    `param(`,
    `    [string]$ComposerRoot,`,
    `    [string]$ResolvedPath`,
    `)`,
    `$ErrorActionPreference = "Stop"`,
    `Write-Host "  組裝系統（這是最耗時的步驟）..."`,
    `& powershell -ExecutionPolicy Bypass -File (Join-Path $ComposerRoot "tools\\assemble-system.ps1") \``,
    `    -ResolvedPlanPath $ResolvedPath`,
    `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`,
    `Write-Host "  ✓ 系統組裝完成"`,
  ];
  return L.join("\r\n");
}

function buildDeployPhase4Ps1() {
  const L = [
    `# ${"═".repeat(56)}`,
    `#  階段 4：打包 client deploy ZIP`,
    `# ${"═".repeat(56)}`,
    `param(`,
    `    [string]$ComposerRoot,`,
    `    [string]$RecipeName`,
    `)`,
    `$ErrorActionPreference = "Stop"`,
    `Write-Host "  打包 client deploy ZIP..."`,
    `& powershell -ExecutionPolicy Bypass -File (Join-Path $ComposerRoot "tools\\package-client-deploy.ps1") \``,
    `    -RecipeName $RecipeName`,
    `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`,
    `$ClientZip = Join-Path $ComposerRoot "dist\\client-deploy-$RecipeName.zip"`,
    `Write-Host "  ✓ Client deploy ZIP：$ClientZip"`,
  ];
  return L.join("\r\n");
}

function buildDeploySh(recipe, dateStr) {
  const kits = recipe.enabledKits.join(", ");
  const name = recipe.name;
  const db = recipe.database.engine;
  const L = [
    `#!/usr/bin/env bash`,
    `# ${"═".repeat(64)}`,
    `#  Form System Kit Composer — 伺服器部署腳本 (Linux / macOS)`,
    `#  Recipe : ${name}`,
    `#  產生於 : ${dateStr}`,
    `#  Kits   : ${kits}`,
    `#  DB     : ${db}`,
    `# ${"═".repeat(64)}`,
    `#`,
    `#  ── 前置作業（Windows 開發機）──────────────────────────`,
    `#  1. 在 kit-composer 執行：`,
    `#       .\\tools\\assemble-system.ps1`,
    `#     → 產生 dist\\generated-system\\`,
    `#  2. 將整個 dist\\generated-system\\ 複製到伺服器，例如：`,
    `#       scp -r dist/generated-system user@host:/opt/form-system`,
    `#`,
    `#  ── 伺服器端用法 ────────────────────────────────────────`,
    `#    bash deploy.sh /opt/form-system          # 指定系統目錄`,
    `#    bash deploy.sh                           # 自動找腳本旁的 system/`,
    `#    bash deploy.sh /opt/form-system --background  # 完成後背景啟動`,
    ``,
    `set -uo pipefail`,
    ``,
    `# ── 工具函式`,
    `die()  { echo "" >&2; echo "[ERROR] $*" >&2; echo "" >&2; exit 1; }`,
    `info() { echo "  $*"; }`,
    `ok()   { echo "  ✓ $*"; }`,
    ``,
    `_MISSING=0`,
    `check_cmd() {`,
    `    if command -v "$1" &>/dev/null; then`,
    `        ok "$1  $($1 --version 2>/dev/null | head -1)"`,
    `    else`,
    `        info "✗ $1  未安裝 → $2"`,
    `        _MISSING=$((_MISSING + 1))`,
    `    fi`,
    `}`,
    ``,
    `check_prerequisites() {`,
    `    echo "=== 前置套件檢查 ==="`,
    `    _MISSING=0`,
    `    check_cmd python3 "https://www.python.org/downloads/"`,
    `    check_cmd pip3    "隨 Python 安裝：python3 -m ensurepip"`,
    `    check_cmd node    "https://nodejs.org/"`,
    `    check_cmd npm     "隨 Node.js 一同安裝"`,
    `    echo ""`,
    `    if [ "\${_MISSING}" -gt 0 ]; then`,
    `        die "\${_MISSING} 個必要套件未安裝，請安裝後重試。"`,
    `    fi`,
    `    ok "所有前置套件就緒"`,
    `    echo ""`,
    `}`,
    ``,
    `# ── 參數解析（旗標與路徑分開，順序不限）`,
    `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"`,
    `SYS_ROOT=""`,
    `BACKGROUND=0`,
    `for _arg in "$@"; do`,
    `    case "$_arg" in`,
    `        --background) BACKGROUND=1 ;;`,
    `        --*) die "未知選項: $_arg" ;;`,
    `        *) SYS_ROOT="$_arg" ;;`,
    `    esac`,
    `done`,
    ``,
    `# ── 系統目錄解析：未傳入路徑時自動找腳本旁的 system/ 或 generated-system/`,
    `if [ -z "\${SYS_ROOT}" ]; then`,
    `    for _c in "$SCRIPT_DIR/system" "$SCRIPT_DIR/generated-system"; do`,
    `        if [ -d "$_c" ]; then SYS_ROOT="$_c"; break; fi`,
    `    done`,
    `fi`,
    `if [ -z "\${SYS_ROOT}" ]; then`,
    `    die "找不到系統目錄。用法：bash deploy.sh /path/to/generated-system"`,
    `fi`,
    `if [ ! -d "\${SYS_ROOT}" ]; then`,
    `    die "目錄不存在：\${SYS_ROOT}"`,
    `fi`,
    `SYS_ROOT="$(cd "\${SYS_ROOT}" && pwd)"`,
    ``,
    `# ── 驗證是 form-system 組裝輸出`,
    `if [ ! -f "\${SYS_ROOT}/backend/requirements.txt" ]; then`,
    `    die "找不到 backend/requirements.txt，請確認路徑是 dist/generated-system 目錄。"`,
    `fi`,
    ``,
    `echo ""`,
    `echo "Form System Kit Composer 部署程序"`,
    `echo "Recipe  : ${name}"`,
    `echo "SysRoot : \${SYS_ROOT}"`,
    `echo ""`,
    ``,
    `# ═══════════════════════════════════════════════════════`,
    `# 1. 前置套件偵測`,
    `# ═══════════════════════════════════════════════════════`,
    `check_prerequisites`,
    ``,
    `# ═══════════════════════════════════════════════════════`,
    `# 2. 虛擬環境與依賴安裝`,
    `# ═══════════════════════════════════════════════════════`,
    `echo "=== 設定虛擬環境 ==="`,
    `VENV="\${SYS_ROOT}/.venv"`,
    `python3 -m venv --clear "\${VENV}" || die "建立虛擬環境失敗。請執行：sudo apt install python3-venv"`,
    `"\${VENV}/bin/pip" install --quiet --upgrade pip`,
    `ok "虛擬環境：\${VENV}"`,
    `echo ""`,
    `echo "=== 安裝後端依賴 ==="`,
    `"\${VENV}/bin/pip" install --quiet -r "\${SYS_ROOT}/backend/requirements.txt"`,
    `ok "後端依賴安裝完成"`,
    `if [ -f "\${SYS_ROOT}/frontend/package.json" ]; then`,
    `    npm --prefix "\${SYS_ROOT}/frontend" install`,
    `    ok "前端依賴安裝完成"`,
    `fi`,
    `echo ""`,
    ``,
    `# ═══════════════════════════════════════════════════════`,
    `# 3. 資料庫遷移`,
    `# ═══════════════════════════════════════════════════════`,
    `echo "=== 資料庫遷移 ==="`,
    `if [ -f "\${SCRIPT_DIR}/deploy-init.env" ]; then`,
    `    info "偵測到 deploy-init.env，自動套用憑證..."`,
    `    set -a; . "\${SCRIPT_DIR}/deploy-init.env"; set +a`,
    `    cp "\${SCRIPT_DIR}/deploy-init.env" "\${SYS_ROOT}/.env"`,
    `    ok "已從 deploy-init.env 載入憑證"`,
    `elif [ -f "\${SYS_ROOT}/.env" ]; then`,
    `    set -a && . "\${SYS_ROOT}/.env" && set +a`,
    `    info "已載入 \${SYS_ROOT}/.env"`,
    `fi`,
    `if [ -z "\${DATABASE_URL:-}" ]; then`,
    `    die "DATABASE_URL 未設定。\\n請建立 \${SYS_ROOT}/.env 並填入連線字串：\\n  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname"`,
    `fi`,
    `if [ -f "\${SYS_ROOT}/backend/alembic.ini" ]; then`,
    `    (cd "\${SYS_ROOT}/backend" && "\${VENV}/bin/python" -m alembic upgrade head)`,
    `elif [ -f "\${SYS_ROOT}/backend/app/core/generated_db_bootstrap.py" ]; then`,
    `    (cd "\${SYS_ROOT}/backend" && "\${VENV}/bin/python" -m app.core.generated_db_bootstrap)`,
    `else`,
    `    die "找不到 migration 工具（alembic.ini 或 generated_db_bootstrap.py）"`,
    `fi`,
    `ok "資料庫遷移完成"`,
    `echo ""`,
    ``,
    `# ═══════════════════════════════════════════════════════`,
    `# 4. 啟動`,
    `# ═══════════════════════════════════════════════════════`,
    `echo "=== 部署完成 ==="`,
    `if [ "\${BACKGROUND}" -eq 1 ]; then`,
    `    mkdir -p "\${SYS_ROOT}/logs"`,
    `    (cd "\${SYS_ROOT}/backend" && nohup "\${VENV}/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "\${SYS_ROOT}/logs/backend.log" 2>&1 &`,
    `    echo "$!" > "\${SYS_ROOT}/logs/backend.pid")`,
    `    ok "後端已在背景啟動  port=8000"`,
    `    info "日誌：\${SYS_ROOT}/logs/backend.log"`,
    `    if [ -f "\${SYS_ROOT}/frontend/package.json" ]; then`,
    `        info "前端：cd \${SYS_ROOT}/frontend && npm run dev"`,
    `    fi`,
    `else`,
    `    info "啟動後端："`,
    `    info "  cd \${SYS_ROOT}/backend && \${VENV}/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"`,
    `    info "  cd \${SYS_ROOT}/backend && \${VENV}/bin/python -m uvicorn app.main:app --reload  # 開發模式"`,
    `    if [ -f "\${SYS_ROOT}/frontend/package.json" ]; then`,
    `        info "啟動前端："`,
    `        info "  cd \${SYS_ROOT}/frontend && npm run dev"`,
    `    fi`,
    `fi`,
    `echo ""`,
    `# ═══════════════════════════════════════════════════════`,
    `# ⚠ 生產環境注意事項`,
    `# ═══════════════════════════════════════════════════════`,
    `echo "──────────────────────────────────────────────────────"`,
    `echo "  ⚠  生產環境上線前，請確認以下項目："`,
    `echo "──────────────────────────────────────────────────────"`,
    `info "1. 勿以 root 執行 uvicorn — 建立專用低權限帳號："`,
    `info "     sudo useradd -r -s /bin/false form-system"`,
    `info "2. uvicorn 不提供 TLS — 生產環境需在前方架 reverse proxy："`,
    `info "     nginx + certbot (Let's Encrypt)  或  Caddy"`,
    `info "3. 確認 .env 中 DATABASE_URL 使用強密碼，非預設值"`,
    `info "4. 設定 ENVIRONMENT=production 以關閉 /docs 及 /openapi.json"`,
    `info "5. 執行 pip-audit 與 npm audit 確認依賴無已知 CVE"`,
    `echo ""`,
    `if command -v systemctl >/dev/null 2>&1; then`,
    `    echo "──────────────────────────────────────────────────────"`,
    `    info "偵測到 systemctl。若要設定開機自啟（需 root）："`,
    `    info "  sudo sed -i 's|__SYS_ROOT__|'\${SYS_ROOT}'|g' \${SCRIPT_DIR}/form-system.service"`,
    `    info "  sudo cp \${SCRIPT_DIR}/form-system.service /etc/systemd/system/"`,
    `    info "  sudo systemctl daemon-reload && sudo systemctl enable --now form-system"`,
    `    echo ""`,
    `fi`,
  ];
  return L.join("\n");
}

function buildDeployReadme(recipe, dateStr) {
  const flows = recipe.selectedFlows.join("、") || "（未選擇）";
  const kits = recipe.enabledKits;
  const db = recipe.database.engine;
  const name = recipe.name;
  const tables = recipe.tableSchemas.length
    ? recipe.tableSchemas.map((t) => `- \`${t.tableName}\`（${t.columns.length} 欄）`).join("\n")
    : "（未上傳）";

  const kitLines = kits.map((k) => `- \`${k}\``).join("\n");

  return `# Form System 部署套件

| 項目 | 內容 |
|------|------|
| Recipe | \`${name}\` |
| 產生於 | ${dateStr} |
| 業務流程 | ${flows} |
| DB 引擎 | ${db} |
| Kit 數量 | ${kits.length} |

## 快速開始（在 Kit Composer 開發機上執行）

> 此 ZIP 為 **開發人員用**，需在安裝有 \`form-system-kit-composer\` 專案的 Windows 機器上執行。

\`\`\`powershell
# 在 form-system-kit-composer 專案根目錄執行
powershell -ExecutionPolicy Bypass -File deploy.ps1

# 若中途失敗，可從指定階段重試（不必重頭）
powershell -ExecutionPolicy Bypass -File deploy.ps1 -StartFrom 3
\`\`\`

執行完成後，將產生 **client deploy ZIP**（位於 \`dist/\` 目錄）。

## 組裝階段說明

| 階段 | 腳本 | 說明 |
|------|------|------|
| 1 | \`phases/01-prepare.ps1\` | 複製 recipe.json 並驗證格式 |
| 2 | \`phases/02-resolve.ps1\` | 解析 kit 依賴、產生 resolved-plan |
| 3 | \`phases/03-assemble.ps1\` | 組裝系統（最耗時，失敗可 -StartFrom 3 重試） |
| 4 | \`phases/04-package.ps1\` | 打包 client deploy ZIP |

## 部署到目標機器（Client Deploy ZIP）

解壓後選擇安裝方式：

### Option A：Web 安裝精靈（推薦）

**Windows**（無需安裝 Python）：
\`\`\`
雙擊 install-wizard.exe
\`\`\`

**Linux / macOS**：
\`\`\`bash
python3 install-wizard.py
\`\`\`

瀏覽器自動開啟 \`http://localhost:9981/\`，依 7 步驟引導完成安裝設定。

### Option B：命令列安裝

\`\`\`powershell
# Windows
powershell -ExecutionPolicy Bypass -File deploy.ps1
\`\`\`

\`\`\`bash
# Linux / macOS
bash deploy.sh --wizard   # 互動式引導（推薦首次安裝）
bash deploy.sh            # 直接安裝（需已設定 .env）
\`\`\`

## 前置需求

| 工具 | 最低版本 |
|------|---------|
| Python | 3.9+ |
| Node.js | 18+ |
| ${db === "postgresql" ? "PostgreSQL" : db === "sqlite" ? "SQLite（內建）" : db} | ${db === "postgresql" ? "14+" : "—"} |
| PowerShell | 7+（Windows 內建 5.1 亦可） |

## 包含的 Kit

${kitLines}

## 上傳的資料表

${tables}

## 目標機器部署完成後

系統啟動後預設端點（目標機器）：

- 後端 API：\`http://localhost:8000\`
- API 文件：\`http://localhost:8000/docs\`
- 前端介面：\`http://localhost:5173\`（開發模式）

管理部署狀態（在解壓目錄的 \`system/\` 下執行）：

\`\`\`powershell
.\\scripts\\status.ps1    # 查看運作狀態
.\\scripts\\stop.ps1      # 停止
.\\scripts\\restart.ps1   # 重啟
\`\`\`
`;
}

async function downloadPackage() {
  const btn = document.querySelector("#download-package");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  btn.textContent = "打包中…";

  try {
    if (typeof JSZip === "undefined") throw new Error("JSZip 未載入");
    const manifestResp = await fetch("/api/package-manifest");
    if (manifestResp.ok) {
      const manifest = await manifestResp.json();
      if (manifest && manifest.ok === false) {
        throw new Error(`Package incomplete: missing ${(manifest.missing || []).join(", ")}. Run tools/build-wizard-exe.ps1 before packaging.`);
      }
    } else if (manifestResp.status === 422) {
      const manifest = await manifestResp.json().catch(() => ({}));
      throw new Error(manifest.message || "Package incomplete. Run tools/build-wizard-exe.ps1 before packaging.");
    }
    const recipe = buildRecipe();
    const dateStr = new Date().toISOString().slice(0, 16).replace("T", " ");
    const zip = new JSZip();
    // UTF-8 BOM: PowerShell 5.1 needs BOM to detect UTF-8; without it Chinese chars
    // are read as CP950/ANSI, corrupting brace-matching (MissingEndCurlyBrace).
    const bom = "﻿";
    zip.file("recipe.json", recipeJsonText());
    zip.file("deploy.ps1", bom + buildDeployPs1(recipe, dateStr));
    zip.file("phases/01-prepare.ps1", bom + buildDeployPhase1Ps1());
    zip.file("phases/02-resolve.ps1", bom + buildDeployPhase2Ps1());
    zip.file("phases/03-assemble.ps1", bom + buildDeployPhase3Ps1());
    zip.file("phases/04-package.ps1", bom + buildDeployPhase4Ps1());
    zip.file("deploy.sh", buildDeploySh(recipe, dateStr));
    zip.file("README.md", buildDeployReadme(recipe, dateStr));
    if (state.machinePubkey) {
      zip.file("machine-pubkey.pem", state.machinePubkey + "\n");
    }
    // Include install-wizard files when served via serve-gui.cjs
    try {
      const pyResp = await fetch("/api/wizard-py");
      if (pyResp.ok) zip.file("install-wizard.py", await pyResp.text());
    } catch (_) { /* server not running, skip */ }
    try {
      const exeResp = await fetch("/api/wizard-exe");
      if (exeResp.ok) zip.file("install-wizard.exe", await exeResp.arrayBuffer());
    } catch (_) { /* exe not built yet or server not running, skip */ }

    // ── system/ bundle（install-wizard 路徑驗證需要 system/backend/requirements.txt）──
    try {
      btn.textContent = "打包 system…";
      const sysResp = await fetch("/api/system-bundle");
      if (sysResp.ok) {
        const data = await sysResp.json();
        if (data.available && Array.isArray(data.files)) {
          for (const f of data.files) {
            // base64 → Uint8Array，放入 system/<relpath>
            const bin = atob(f.b64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            zip.file("system/" + f.path, bytes);
          }
        }
      }
    } catch (_) { /* server not running or no system dir, skip */ }

    // ── license.lic（偵測到 issuer 私鑰且已登錄 TPM 公鑰時自動簽發）──
    if (state.machinePubkey) {
      try {
        btn.textContent = "簽發授權…";
        const licResp = await fetch("/api/issue-license", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pubkey: state.machinePubkey, days: 365 }),
        });
        if (licResp.ok) {
          const data = await licResp.json();
          if (data.ok && data.license) {
            zip.file("system/license.lic", JSON.stringify(data.license, null, 2));
          }
        }
      } catch (_) { /* issuer key not configured, skip — license can be added manually */ }
    }

    btn.textContent = "壓縮中…";
    const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${recipe.name}-deploy-${new Date().toISOString().slice(0, 10)}.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    recordOperation("download-package");
    btn.textContent = "已下載";
    setTimeout(() => { btn.textContent = "下載 .zip"; btn.disabled = false; }, 2000);
  } catch (err) {
    console.error("downloadPackage failed:", err);
    alert(err instanceof Error ? err.message : String(err));
    btn.textContent = "下載失敗";
    setTimeout(() => { btn.textContent = "下載 .zip"; btn.disabled = false; }, 2000);
  }
}

function recordOperation(action, extra = {}) {
  const recipe = buildRecipe();
  const body = JSON.stringify({
    action,
    recipeName: recipe.name,
    kits: recipe.enabledKits,
    licensee: "",
    ...extra,
  });
  fetch("/api/log", { method: "POST", headers: { "Content-Type": "application/json" }, body })
    .catch(() => {});
}

// ── 工具函式 ──────────────────────────────────────────────────────────────────
function selectedKits() {
  return state.kits.filter((item) => state.selected.has(item.id));
}

function selectedSubfeatures(item) {
  const selected = state.selectedSubfeatures.get(item.id);
  if (!selected) return [];
  return subfeatureList(item).filter((subfeature) => selected.has(subfeature.id));
}

function subfeatureOptionValue(subfeature, option) {
  const key = subfeatureKey(subfeature.parentId, subfeature.id);
  const values = state.subfeatureOptions.get(key) || {};
  return Object.prototype.hasOwnProperty.call(values, option.id) ? values[option.id] : option.defaultValue;
}

function subfeatureKey(kitId, subfeatureId) {
  return `${kitId}::${subfeatureId}`;
}

function parseSubfeatureKey(key) {
  const [kitId, subfeatureId] = key.split("::");
  return { kitId, subfeatureId };
}

function findKit(id) {
  return state.kits.find((item) => item.id === id);
}

function keepActivePreviewSelected() {
  if (!selectedKits().some((item) => item.id === state.activePreviewKit)) {
    state.activePreviewKit = selectedKits()[0]?.id || "";
  }
}

window.buildRecipe = buildRecipe;
