package com.localcoop.phonepad.tests;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import com.localcoop.phonepad.MainActivity;

public class TouchTests extends Instrumentation {
    private Bundle args;
    private MainActivity activity;
    private long down;
    private int assertions;
    @Override public void onCreate(Bundle values) {super.onCreate(values);args=values;start();}
    private void check(boolean value,String label) {assertions++;if(!value)throw new AssertionError(label);}
    private void event(int action,int[] ids,float[] xs,float[] ys) {
        MainActivity.PadView pad=activity.getPadView();
        MotionEvent.PointerProperties[] properties=new MotionEvent.PointerProperties[ids.length];
        MotionEvent.PointerCoords[] points=new MotionEvent.PointerCoords[ids.length];
        for(int i=0;i<ids.length;i++) {
            properties[i]=new MotionEvent.PointerProperties();properties[i].id=ids[i];properties[i].toolType=MotionEvent.TOOL_TYPE_FINGER;
            points[i]=new MotionEvent.PointerCoords();points[i].x=pad.screenX(xs[i]);points[i].y=pad.screenY(ys[i]);points[i].pressure=1;points[i].size=1;
        }
        if(action==MotionEvent.ACTION_DOWN)down=SystemClock.uptimeMillis();
        MotionEvent touch=MotionEvent.obtain(down,SystemClock.uptimeMillis(),action,ids.length,properties,points,0,0,1,1,0,0,InputDevice.SOURCE_TOUCHSCREEN,0);
        pad.dispatchTouchEvent(touch);touch.recycle();
    }
    private MainActivity.State state() {return activity.getPadView().snapshot();}
    @Override public void onStart() {
        Bundle result=new Bundle();
        try {
            Intent intent=new Intent().setClassName("com.localcoop.phonepad","com.localcoop.phonepad.MainActivity")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity=(MainActivity)startActivitySync(intent);
            waitForIdleSync();SystemClock.sleep(300);
            runOnMainSync(() -> {
                event(0,new int[]{4},new float[]{185},new float[]{365});
                event(2,new int[]{4},new float[]{270},new float[]{280});
                event(5|(1<<8),new int[]{4,9},new float[]{270,1007},new float[]{280,394});
                check(state().lx>.5f && state().ly>.5f,"left stick diagonal plus A");
                check((state().buttons&0x1000)!=0,"A held concurrently with stick");
            });
            SystemClock.sleep(500);
            runOnMainSync(() -> {
                event(6,new int[]{4,9},new float[]{270,1007},new float[]{280,394});
                check(state().lx==0 && state().ly==0,"lifting stick returns to neutral");
                check(state().buttons==0x1000,"lifting stick retains other finger on A");
            });
            SystemClock.sleep(300);
            runOnMainSync(() -> {
                event(1,new int[]{9},new float[]{1007},new float[]{394});
                check(state().buttons==0,"last finger releases A");
                event(0,new int[]{2},new float[]{1007},new float[]{394});
                event(5|(1<<8),new int[]{2,7},new float[]{1007,1007},new float[]{394,394});
                event(6,new int[]{2,7},new float[]{1007,1007},new float[]{394,394});
                check(state().buttons==0x1000,"two fingers on one button retains second hold");
                event(3,new int[]{7},new float[]{1007},new float[]{394});
                check(state().buttons==0,"cancel clears every button");
                event(0,new int[]{3},new float[]{290},new float[]{142});
                event(5|(1<<8),new int[]{3,8},new float[]{290,1083},new float[]{142,142});
                check(state().lt==1 && (state().buttons&0x200)!=0,"trigger plus shoulder multitouch");
                event(3,new int[]{3,8},new float[]{290,1083},new float[]{142,142});
                check(state().lt==0 && state().buttons==0,"cancel releases trigger and shoulder");
                event(0,new int[]{6},new float[]{765},new float[]{425});
                event(2,new int[]{6},new float[]{690},new float[]{490});
                check(state().rx<-.5f && state().ry<-.5f,"right stick independent direction");
                activity.getPadView().releaseAll();
                check(state().rx==0 && state().ry==0,"lifecycle release resets right stick");
                getTargetContext().getSharedPreferences("settings",0).edit().putString("map.A","Y").commit();
                try {
                    event(0,new int[]{5},new float[]{1007},new float[]{394});
                    check(state().buttons==0x8000,"custom A position maps to Y");
                    activity.getPadView().releaseAll();
                } finally {getTargetContext().getSharedPreferences("settings",0).edit().remove("map.A").commit();}
            });
            result.putString("stream","PASS: "+assertions+" touch assertions on physical Android phone");
            finish(Activity.RESULT_OK,result);
        } catch(Throwable error) {
            result.putString("stream","FAIL: "+error.toString());finish(Activity.RESULT_CANCELED,result);
        }
    }
}
