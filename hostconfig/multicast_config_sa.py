disable = False

print 'vlan 1'
#for i in range(40):
#    for j in range(2):
#        print 'no ip igmp snooping static-group 224.0.2.%d interface ethernet 1/%d/%d'%(128+2*i+j, i//4+1, i%4 +1)

port_map = [1,3,5,7,9,2,4,6,8,10]
subport_map = [
[1,2,3,4],
[4,2,3,1],
[1,2,3,4],
[1,2,3,4],
[1,2,3,4],
[1,2,3,4],
[1,2,3,4],
[1,2,3,4],
[1,2,3,4],
[1,2,3,4],
]

cpu_port = 11
cpu_subport = 1

for i in range(40):
    for j in range(2):
        if disable:
            print 'no',
        print 'ip igmp snooping static-group 224.0.2.%d interface ethernet 1/%d/%d'%(128+2*i+j, port_map[i//4], subport_map[i//4][i%4])

for i in range(40):
    if disable:
        print 'no',
    print 'ip igmp snooping static-group 224.0.2.%d interface ethernet 1/%d/%d'%(128+2*i+1, cpu_port, cpu_subport)

