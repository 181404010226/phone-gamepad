package com.localcoop.phonepad;

import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.BooleanSupplier;
import org.json.JSONObject;

/** The same discovery implementation is exercised on Android and by desktop JVM tests. */
public final class LanDiscovery {
    public static final class Result {
        public final String host, name;
        public final int port;
        public final boolean full;
        Result(String h,int p,String n,boolean f) {host=h;port=p;name=n;full=f;}
    }
    public static Result find(String client,String previous,BooleanSupplier keepGoing) throws Exception {
        return find(client,previous,keepGoing,26761);
    }
    public static Result find(String client,String previous,BooleanSupplier keepGoing,int discoveryPort) throws Exception {
        boolean sawFull=false;
        Result candidate=null;
        try(DatagramSocket socket=new DatagramSocket()) {
            socket.setBroadcast(true);
            socket.setSoTimeout(100);
            LinkedHashSet<String> destinations=new LinkedHashSet<>();
            if(previous.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}"))destinations.add(previous);
            Enumeration<NetworkInterface> interfaces=NetworkInterface.getNetworkInterfaces();
            while(interfaces!=null && interfaces.hasMoreElements()) {
                NetworkInterface network=interfaces.nextElement();
                if(!network.isUp() || network.isLoopback())continue;
                for(InterfaceAddress address:network.getInterfaceAddresses())
                    if(address.getBroadcast()!=null)destinations.add(address.getBroadcast().getHostAddress());
            }
            destinations.add("255.255.255.255");
            byte[] query=new JSONObject().put("v",2).put("type","discover").put("client",client)
                .toString().getBytes(StandardCharsets.UTF_8);
            for(String target:destinations) {
                if(!keepGoing.getAsBoolean())return new Result(null,0,"",false);
                try {socket.send(new DatagramPacket(query,query.length,InetAddress.getByName(target),discoveryPort));}
                catch(Exception ignored) { }
            }
            long until=System.nanoTime()+750000000L;
            while(keepGoing.getAsBoolean() && System.nanoTime()<until) {
                byte[] buffer=new byte[1500];DatagramPacket reply=new DatagramPacket(buffer,buffer.length);
                try {
                    socket.receive(reply);
                    JSONObject found=new JSONObject(new String(reply.getData(),0,reply.getLength(),StandardCharsets.UTF_8));
                    if(found.optInt("v")!=2 || !"host".equals(found.optString("type")) || found.optInt("max_players")!=4)continue;
                    int port=found.optInt("port");if(port<1 || port>65535 || reply.getPort()!=port)continue;
                    if(found.optInt("available")<=0 && found.optInt("player")<=0) {sawFull=true;continue;}
                    String host=reply.getAddress().getHostAddress();
                    Result next=new Result(host,port,found.optString("name","电脑"),false);
                    if(host.equals(previous))return next;
                    if(candidate==null)candidate=next;
                } catch(SocketTimeoutException ignored) { }
                catch(org.json.JSONException ignored) { }
            }
        }
        return candidate!=null?candidate:new Result(null,0,"",sawFull);
    }
}
