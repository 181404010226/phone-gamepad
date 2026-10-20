package com.localcoop.phonepad;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.*;
import android.os.Bundle;
import android.os.Build;
import android.os.SystemClock;
import android.util.SparseArray;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class MainActivity extends Activity {
    private PadView pad;
    private Transport transport;
    private SharedPreferences prefs;
    private boolean dialogOpen;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON | WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(5894);
        prefs = getSharedPreferences("settings", MODE_PRIVATE);
        prefs.edit().remove("pin").remove("player").apply();
        transport = new Transport();
        pad = new PadView();
        setContentView(pad);
        String client = prefs.getString("client", "");
        if (client.isEmpty()) prefs.edit().putString("client", UUID.randomUUID().toString()).apply();
        transport.start();
    }

    public PadView getPadView() { return pad; }

    private void showConnection() {
        if (dialogOpen || isFinishing()) return;
        dialogOpen = true;
        pad.releaseAll();
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int margin = (int)(20 * getResources().getDisplayMetrics().density);
        body.setPadding(margin, margin / 2, margin, margin / 2);
        TextView help = new TextView(this);
        help.setText("手机与电脑连接同一 Wi-Fi，打开电脑接收端即可自动匹配。\n最多四台手机，按连接顺序自动分配玩家 1～4。无需配对码或选择玩家。");
        body.addView(help);
        TextView detail = new TextView(this);
        detail.setPadding(0, margin, 0, margin);
        body.addView(detail);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("四人自动匹配")
            .setView(body).setPositiveButton("重新匹配", (d,w) -> transport.rematch())
            .setNeutralButton("自定义按键", (d,w) -> pad.post(this::showMapping))
            .setNegativeButton("返回手柄", null).create();
        dialog.setOnDismissListener(d -> { dialogOpen=false; pad.releaseAll(); });
        dialog.setOnShowListener(d -> pad.post(new Runnable() {
            @Override public void run() {
                if (!dialog.isShowing()) return;
                Config c=transport.config;
                detail.setText(transport.status + (c==null ? "" : "\n电脑："+c.name+"  ("+c.host+")") +
                    (transport.assignedPlayer>0 ? "\n已分配玩家 "+transport.assignedPlayer : "\n正在等待空闲玩家位…"));
                pad.postDelayed(this,300);
            }
        }));
        dialog.show();
    }

    private final String[] mappingIds={"A","B","X","Y","LB","RB","LT","RT","BACK","START","LS","RS"};
    private final String[] mappingChoices={"A","B","X","Y","LB","RB","LT","RT","BACK","START","LS","RS","↑","↓","←","→","禁用"};
    private String mapped(String id) { return prefs.getString("map."+id,id); }
    private void showMapping() {
        dialogOpen=true;
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
        int margin=(int)(16*getResources().getDisplayMetrics().density);body.setPadding(margin,margin,margin,margin);
        TextView help=new TextView(this);help.setText("选择每个触控位置实际发送的手柄动作。保存后，手柄界面会显示新的按钮名称。");body.addView(help);
        ArrayList<String> choices=new ArrayList<>();
        for(String id:mappingIds) {
            LinearLayout row=new LinearLayout(this);row.setOrientation(LinearLayout.HORIZONTAL);
            TextView label=new TextView(this);label.setText(id+" 位置");row.addView(label,new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1));
            final int index=choices.size();choices.add(mapped(id));
            Button choose=new Button(this);choose.setText(mapped(id));
            choose.setOnClickListener(v->new AlertDialog.Builder(this).setTitle(id+" 位置的动作")
                .setItems(mappingChoices,(d,w)->{choices.set(index,mappingChoices[w]);choose.setText(mappingChoices[w]);}).show());
            row.addView(choose,new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1));body.addView(row);
        }
        ScrollView scroll=new ScrollView(this);scroll.addView(body);
        LinearLayout form=new LinearLayout(this);
        form.addView(scroll,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
            (int)(getResources().getDisplayMetrics().heightPixels*.55f)));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("自定义按钮")
            .setView(form).setPositiveButton("保存",(d,w)->{
                SharedPreferences.Editor editor=prefs.edit();
                for(int i=0;i<mappingIds.length;i++)editor.putString("map."+mappingIds[i],choices.get(i));
                editor.apply();pad.releaseAll();
            }).setNeutralButton("恢复默认",(d,w)->{
                SharedPreferences.Editor editor=prefs.edit();for(String id:mappingIds)editor.remove("map."+id);editor.apply();pad.releaseAll();
            }).setNegativeButton("取消",null).create();
        dialog.setOnDismissListener(d->{dialogOpen=false;pad.postDelayed(this::showConnection,100);});
        dialog.show();
    }

    @Override protected void onResume() {
        super.onResume();
        if (transport != null) transport.resumeMatching();
    }

    @Override protected void onPause() {
        if (pad != null) pad.releaseAll();
        if (transport != null) transport.disconnect();
        super.onPause();
    }
    @Override public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (!focus && pad != null) pad.releaseAll();
        if (focus) getWindow().getDecorView().setSystemUiVisibility(5894);
    }
    @Override public void onBackPressed() { showConnection(); }
    @Override protected void onDestroy() {
        transport.closed = true;
        transport.disconnect();
        super.onDestroy();
    }

    public static class State {
        public final int buttons;
        public final float lx, ly, rx, ry, lt, rt;
        State(int b, float x, float y, float u, float v, float l, float r) {
            buttons=b; lx=x; ly=y; rx=u; ry=v; lt=l; rt=r;
        }
    }

    private static class Config {
        final String host, name, client, session=UUID.randomUUID().toString();
        final int port;
        Config(String h, int p, String n, String c) {host=h;port=p;name=n;client=c;}
    }

    private class Transport extends Thread {
        volatile boolean closed, enabled;
        volatile Config config;
        volatile long lastAck;
        volatile int assignedPlayer, latency, generation;
        volatile String status="正在自动查找电脑接收端…", mode="";
        Transport() {super("LANGamepad");}
        void resumeMatching() {enabled=true;}
        void rematch() {
            generation++;
            config=null;
            assignedPlayer=0;
            lastAck=0;
            mode="";
            status="正在自动查找电脑接收端…";
            pad.releaseAll();
        }
        void disconnect() {
            enabled=false;
            generation++;
            config=null;
            assignedPlayer=0;
            lastAck=0;
            status="已暂停 · 返回应用后自动匹配";
            if(pad!=null)pad.postInvalidate();
        }
        JSONObject message(Config c,long seq,MainActivity.State s,String type) throws Exception {
            return new JSONObject().put("v",2).put("type",type).put("client",c.client)
                .put("session",c.session).put("seq",seq).put("name",Build.MODEL).put("buttons",s.buttons)
                .put("lx",s.lx).put("ly",s.ly).put("rx",s.rx).put("ry",s.ry).put("lt",s.lt).put("rt",s.rt);
        }
        void send(DatagramSocket socket,InetAddress host,int port,JSONObject data) throws Exception {
            byte[] bytes=data.toString().getBytes(StandardCharsets.UTF_8);
            socket.send(new DatagramPacket(bytes,bytes.length,host,port));
        }
        Config discover(int scanGeneration) {
            String client=prefs.getString("client","");
            String previous=prefs.getString("lastHost",prefs.getString("host",""));
            try {
                LanDiscovery.Result result=LanDiscovery.find(client,previous,
                    () -> enabled && !closed && generation==scanGeneration);
                if(result.host!=null)return new Config(result.host,result.port,result.name,client);
                if(enabled && generation==scanGeneration)
                    status=result.full ? "四个玩家位已满 · 正在等待空位" : "正在查找电脑 · 请打开新版接收端";
            } catch(Exception ignored) {
                if(enabled && generation==scanGeneration)status="正在等待 Wi-Fi · 自动重试中…";
            }
            return null;
        }
        @Override public void run() {
            while(!closed) {
                if(!enabled) {SystemClock.sleep(50);continue;}
                int activeGeneration=generation;
                Config c=discover(activeGeneration);
                if(!enabled || closed || generation!=activeGeneration)continue;
                if(c==null) {pad.postInvalidate();SystemClock.sleep(500);continue;}
                config=c;
                assignedPlayer=0;
                lastAck=0;
                mode="";
                status="已找到 "+c.name+" · 正在自动分配玩家…";
                long seq=0,started=SystemClock.elapsedRealtime();
                DatagramSocket socket=null;InetAddress host=null;boolean remembered=false;
                try {
                    host=InetAddress.getByName(c.host);
                    socket=new DatagramSocket();socket.setSoTimeout(8);
                    byte[] buffer=new byte[1500];
                    while(enabled && !closed && config==c && generation==activeGeneration) {
                        long began=SystemClock.elapsedRealtime();
                        send(socket,host,c.port,message(c,++seq,pad.snapshot(),"state"));
                        try {
                            DatagramPacket reply=new DatagramPacket(buffer,buffer.length);socket.receive(reply);
                            if(reply.getAddress().equals(host) && reply.getPort()==c.port) {
                                JSONObject ack=new JSONObject(new String(reply.getData(),0,reply.getLength(),StandardCharsets.UTF_8));
                                if(ack.optInt("v")!=2)continue;
                                if(ack.optBoolean("ok")) {
                                    int player=ack.optInt("player");
                                    if(player<1 || player>4)continue;
                                    lastAck=SystemClock.elapsedRealtime();assignedPlayer=player;
                                    if(ack.optLong("seq")==seq)latency=(int)(lastAck-began);
                                    mode=ack.optString("mode");
                                    status="xinput".equals(mode) ? "已连接 · 玩家 "+player+" · Xbox 手柄就绪" : "已匹配玩家 "+player+" · 电脑需安装手柄驱动";
                                    if(!remembered) {prefs.edit().putString("lastHost",c.host).apply();remembered=true;}
                                } else {
                                    String error=ack.optString("error");
                                    if("full".equals(error))status="四个玩家位已满 · 正在等待空位";
                                    else if("controller_unavailable".equals(error))status="电脑手柄位置不足 · 请关闭旧映射工具";
                                    else {status="正在重新匹配…";break;}
                                }
                            }
                        } catch(SocketTimeoutException ignored) { }
                        long reference=lastAck>0?lastAck:started;
                        if(SystemClock.elapsedRealtime()-reference>1800) {status="连接中断 · 正在自动重连…";break;}
                        pad.postInvalidate();
                        SystemClock.sleep(Math.max(1,25-(SystemClock.elapsedRealtime()-began)));
                    }
                } catch(Exception error) {status="正在等待 Wi-Fi · 自动重试中…";}
                finally {
                    if(socket!=null) {
                        try {if(host!=null)send(socket,host,c.port,message(c,++seq,new MainActivity.State(0,0,0,0,0,0,0),"bye"));}catch(Exception ignored) { }
                        socket.close();
                    }
                    if(config==c) {config=null;assignedPlayer=0;lastAck=0;}
                    pad.postInvalidate();
                }
                SystemClock.sleep(200);
            }
        }
    }

    private static class Control {
        final String id,label;
        final float x,y,w,h;
        final int bit,color;
        final boolean circle;
        Control(String i,String t,float a,float b,float c,float d,int mask,int ink,boolean round) {
            id=i;label=t;x=a;y=b;w=c;h=d;bit=mask;color=ink;circle=round;
        }
        boolean hit(float px,float py) {
            return circle ? Math.hypot(px-x,py-y)<=w : Math.abs(px-x)<=w/2 && Math.abs(py-y)<=h/2;
        }
    }
    private static class Contact {
        Control control;
        float x,y;
        Contact(Control c,float a,float b) {control=c;x=a;y=b;}
    }

    public class PadView extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        private final ArrayList<Control> controls=new ArrayList<>();
        private final SparseArray<Contact> contacts=new SparseArray<>();
        private volatile State state=new State(0,0,0,0,0,0,0);
        private float scale=1,offsetX,offsetY;
        private final int CYAN=Color.rgb(72,222,216), BG=Color.rgb(10,17,31), WHITE=Color.rgb(233,242,251);
        PadView() {
            super(MainActivity.this);
            setContentDescription("横屏无线游戏手柄，双摇杆、方向键和ABXY多点触控");
            setFocusable(true);
            controls.add(new Control("left","移动",185,365,122,122,0,CYAN,true));
            controls.add(new Control("right","视角",765,425,80,80,0,CYAN,true));
            controls.add(new Control("dpad","十字键",425,395,82,82,0,CYAN,true));
            controls.add(new Control("LB","LB",117,142,150,65,0x100,CYAN,false));
            controls.add(new Control("LT","LT",290,142,150,65,0,CYAN,false));
            controls.add(new Control("RT","RT",910,142,150,65,0,CYAN,false));
            controls.add(new Control("RB","RB",1083,142,150,65,0x200,CYAN,false));
            controls.add(new Control("Y","Y",1007,224,48,48,0x8000,Color.rgb(255,208,84),true));
            controls.add(new Control("X","X",922,309,48,48,0x4000,Color.rgb(84,173,255),true));
            controls.add(new Control("B","B",1092,309,48,48,0x2000,Color.rgb(255,112,126),true));
            controls.add(new Control("A","A",1007,394,48,48,0x1000,Color.rgb(100,230,154),true));
            controls.add(new Control("BACK","BACK",530,247,110,58,0x20,WHITE,false));
            controls.add(new Control("START","START / 加入",671,247,150,58,0x10,CYAN,false));
            controls.add(new Control("LS","L3",540,430,76,54,0x40,WHITE,false));
            controls.add(new Control("RS","R3",637,430,76,54,0x80,WHITE,false));
        }
        public State snapshot() { return state; }
        public float screenX(float x) { return offsetX+x*scale; }
        public float screenY(float y) { return offsetY+y*scale; }
        public void releaseAll() {
            contacts.clear();
            state=new State(0,0,0,0,0,0,0);
            invalidate();
        }
        @Override protected void onSizeChanged(int w,int h,int oldw,int oldh) {
            scale=Math.min(w/1200f,h/600f);
            offsetX=(w-1200*scale)/2;
            offsetY=(h-600*scale)/2;
        }
        private void fill(int color) { paint.setStyle(Paint.Style.FILL);paint.setColor(color);paint.setShader(null); }
        private void stroke(int color,float width) {paint.setStyle(Paint.Style.STROKE);paint.setColor(color);paint.setStrokeWidth(width);paint.setShader(null);}
        private void text(Canvas canvas,String value,float x,float y,float size,int color,boolean bold) {
            fill(color);paint.setTextSize(size);paint.setTypeface(bold?Typeface.create("sans-serif",Typeface.BOLD):Typeface.create("sans-serif",Typeface.NORMAL));
            paint.setTextAlign(Paint.Align.CENTER);canvas.drawText(value,x,y,paint);
        }
        private boolean held(String id) {
            for(int i=0;i<contacts.size();i++) {Contact p=contacts.valueAt(i);if(p.control.id.equals(id) && p.control.hit(p.x,p.y))return true;}
            return false;
        }
        private void stick(Canvas c,Control item,float x,float y) {
            float r=item.w;
            fill(Color.rgb(17,32,49));c.drawCircle(item.x,item.y,r,paint);
            stroke(Color.rgb(41,72,88),2);c.drawCircle(item.x,item.y,r,paint);
            stroke(Color.rgb(28,49,66),1);c.drawCircle(item.x,item.y,r*.74f,paint);
            c.drawLine(item.x-r*.6f,item.y,item.x+r*.6f,item.y,paint);
            c.drawLine(item.x,item.y-r*.6f,item.x,item.y+r*.6f,paint);
            float kx=item.x+x*r*.46f,ky=item.y-y*r*.46f;
            fill(held(item.id)?Color.rgb(36,111,119):Color.rgb(34,57,74));c.drawCircle(kx,ky,r*.48f,paint);
            stroke(held(item.id)?CYAN:Color.rgb(84,126,144),2);c.drawCircle(kx,ky,r*.48f,paint);
            text(c,item.id.equals("left")?"L":"R",kx,ky+10,30,WHITE,true);
            text(c,item.label,item.x,item.y+r+31,19,Color.rgb(113,147,170),false);
        }
        private void dpad(Canvas c,Control item) {
            int[] bits={1,2,4,8};
            float[] xs={item.x,item.x,item.x-48,item.x+48};
            float[] ys={item.y-48,item.y+48,item.y,item.y};
            String[] labels={"↑","↓","←","→"};
            for(int i=0;i<4;i++) {
                boolean on=(state.buttons&bits[i])!=0;
                fill(on?Color.rgb(36,111,119):Color.rgb(29,45,64));
                c.drawRoundRect(xs[i]-25,ys[i]-25,xs[i]+25,ys[i]+25,10,10,paint);
                stroke(on?CYAN:Color.rgb(52,76,96),1.5f);c.drawRoundRect(xs[i]-25,ys[i]-25,xs[i]+25,ys[i]+25,10,10,paint);
                text(c,labels[i],xs[i],ys[i]+9,28,on?WHITE:Color.rgb(143,172,191),false);
            }
            text(c,"方向键",item.x,item.y+116,19,Color.rgb(113,147,170),false);
        }
        @Override protected void onDraw(Canvas canvas) {
            canvas.drawColor(BG);
            canvas.save();canvas.translate(offsetX,offsetY);canvas.scale(scale,scale);
            fill(BG);paint.setShader(new LinearGradient(0,0,1200,600,Color.rgb(14,26,44),BG,Shader.TileMode.CLAMP));
            canvas.drawRect(0,0,1200,600,paint);paint.setShader(null);
            text(canvas,"LAN  PAD",130,53,30,WHITE,true);
            text(canvas,"手机无线手柄",132,80,15,Color.rgb(112,147,174),false);
            Config config=transport.config;
            boolean online=config!=null && transport.lastAck>0 && SystemClock.elapsedRealtime()-transport.lastAck<1200;
            fill(online?("xinput".equals(transport.mode)?CYAN:Color.rgb(255,204,97)):Color.rgb(100,121,146));
            canvas.drawCircle(481,45,5,paint);
            text(canvas,transport.assignedPlayer>0?"玩家 "+transport.assignedPlayer:"自动匹配中",557,53,23,WHITE,true);
            text(canvas,online?transport.latency+" ms  ·  Wi-Fi":"同一 Wi-Fi 直连电脑",590,79,14,Color.rgb(112,147,174),false);
            fill(Color.rgb(25,47,65));canvas.drawRoundRect(930,25,1160,80,18,18,paint);
            stroke(Color.rgb(52,105,123),1);canvas.drawRoundRect(930,25,1160,80,18,18,paint);
            text(canvas,"自动匹配  ⚙",1045,60,21,CYAN,true);
            stroke(Color.rgb(32,50,71),1);canvas.drawLine(40,101,1160,101,paint);
            for(Control item:controls) {
                if(item.id.equals("left")) {stick(canvas,item,state.lx,state.ly);continue;}
                if(item.id.equals("right")) {stick(canvas,item,state.rx,state.ry);continue;}
                if(item.id.equals("dpad")) {dpad(canvas,item);continue;}
                boolean on=held(item.id);
                fill(on?item.color:Color.rgb(25,40,59));
                if(item.circle)canvas.drawCircle(item.x,item.y,item.w,paint);
                else canvas.drawRoundRect(item.x-item.w/2,item.y-item.h/2,item.x+item.w/2,item.y+item.h/2,17,17,paint);
                stroke(on?WHITE:item.color,on?3:1.5f);
                if(item.circle)canvas.drawCircle(item.x,item.y,item.w,paint);
                else canvas.drawRoundRect(item.x-item.w/2,item.y-item.h/2,item.x+item.w/2,item.y+item.h/2,17,17,paint);
                String action=mapped(item.id);
                String label=action.equals(item.id)?item.label:action;
                text(canvas,label,item.x,item.y+(item.circle?14:8),item.circle?(label.length()>2?22:39):20,on?BG:item.color,true);
            }
            text(canvas,"SELECT",530,294,13,Color.rgb(92,122,146),false);
            text(canvas,"按下加入游戏",671,294,13,Color.rgb(92,122,146),false);
            String status=transport.status;
            text(canvas,status,600,554,20,online?("xinput".equals(transport.mode)?CYAN:Color.rgb(255,204,97)):Color.rgb(157,177,198),false);
            text(canvas,"多点触控  /  双摇杆  /  松手回中  /  后台自动暂停",600,582,14,Color.rgb(85,115,139),false);
            canvas.restore();
        }
        private float[] axis(Contact p) {
            float x=(p.x-p.control.x)/p.control.w,y=(p.control.y-p.y)/p.control.w;
            float length=(float)Math.hypot(x,y);
            if(length<.1f)return new float[]{0,0};
            float strength=Math.min(1,(length-.1f)/.9f);
            return new float[]{x/length*strength,y/length*strength};
        }
        private void recompute() {
            int buttons=0;float lx=0,ly=0,rx=0,ry=0,lt=0,rt=0;
            for(int i=0;i<contacts.size();i++) {
                Contact p=contacts.valueAt(i);String id=p.control.id;
                if(id.equals("left") || id.equals("right")) {
                    float[] value=axis(p);
                    if(id.equals("left")){lx=value[0];ly=value[1];}else{rx=value[0];ry=value[1];}
                } else if(id.equals("dpad")) {
                    float x=p.x-p.control.x,y=p.y-p.control.y;
                    if(x>20)buttons|=8;if(x< -20)buttons|=4;
                    if(y>20)buttons|=2;if(y< -20)buttons|=1;
                } else if(p.control.hit(p.x,p.y)) {
                    String action=mapped(id);
                    if(action.equals("LT"))lt=1;
                    else if(action.equals("RT"))rt=1;
                    else {
                        int mask=0;
                        for(Control target:controls)if(target.id.equals(action))mask=target.bit;
                        if(action.equals("↑"))mask=1;else if(action.equals("↓"))mask=2;
                        else if(action.equals("←"))mask=4;else if(action.equals("→"))mask=8;
                        buttons|=mask;
                    }
                }
            }
            state=new State(buttons,lx,ly,rx,ry,lt,rt);invalidate();
        }
        @Override public boolean onTouchEvent(MotionEvent event) {
            int action=event.getActionMasked(),index=event.getActionIndex();
            if(action==MotionEvent.ACTION_CANCEL) {releaseAll();return true;}
            if(action==MotionEvent.ACTION_DOWN || action==MotionEvent.ACTION_POINTER_DOWN) {
                float x=(event.getX(index)-offsetX)/scale,y=(event.getY(index)-offsetY)/scale;
                if(x>=930 && x<=1160 && y>=25 && y<=80) {showConnection();return true;}
                for(Control c:controls) if(c.hit(x,y)) {
                    boolean taken=false;
                    if(c.id.equals("left") || c.id.equals("right")) for(int i=0;i<contacts.size();i++)if(contacts.valueAt(i).control==c)taken=true;
                    if(!taken){contacts.put(event.getPointerId(index),new Contact(c,x,y));if(!c.id.equals("left")&&!c.id.equals("right"))performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);}
                    break;
                }
            }
            for(int i=0;i<event.getPointerCount();i++) {
                Contact p=contacts.get(event.getPointerId(i));
                if(p!=null){p.x=(event.getX(i)-offsetX)/scale;p.y=(event.getY(i)-offsetY)/scale;}
            }
            if(action==MotionEvent.ACTION_UP || action==MotionEvent.ACTION_POINTER_UP)contacts.remove(event.getPointerId(index));
            recompute();
            return true;
        }
    }
}
