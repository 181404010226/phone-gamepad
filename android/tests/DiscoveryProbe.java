import com.localcoop.phonepad.LanDiscovery;
import org.json.JSONObject;

/** JVM harness for the exact LAN discovery class shipped in the APK. */
public class DiscoveryProbe {
    public static void main(String[] args) throws Exception {
        boolean cancelled=args.length>3 && args[3].equals("cancel");
        LanDiscovery.Result result=LanDiscovery.find(args[0],args[1],()->!cancelled,Integer.parseInt(args[2]));
        System.out.println(new JSONObject().put("host",result.host==null?"":result.host)
            .put("port",result.port).put("full",result.full).toString());
    }
}
