##########################################################################
#
#  Copyright (c) 2016, Image Engine Design Inc. All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#      * Redistributions of source code must retain the above
#        copyright notice, this list of conditions and the following
#        disclaimer.
#
#      * Redistributions in binary form must reproduce the above
#        copyright notice, this list of conditions and the following
#        disclaimer in the documentation and/or other materials provided with
#        the distribution.
#
#      * Neither the name of John Haddon nor the names of
#        any other contributors to this software may be used to endorse or
#        promote products derived from this software without specific prior
#        written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
#  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
#  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
#  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
##########################################################################

import os
import ctypes
import unittest

import arnold
import imath

import IECore
import IECoreScene
import IECoreArnold

import GafferTest
import GafferScene

class RendererTest( GafferTest.TestCase ) :

	def testFactory( self ) :

		self.assertTrue( "Arnold" in GafferScene.Private.IECoreScenePreview.Renderer.types() )

		r = GafferScene.Private.IECoreScenePreview.Renderer.create( "Arnold" )
		self.assertTrue( isinstance( r, GafferScene.Private.IECoreScenePreview.Renderer ) )

	def testSceneDescription( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		o = r.object(
			"testPlane",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject() ),
		)
		o.transform( imath.M44f().translate( imath.V3f( 1, 2, 3 ) ) )
		del o

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			n = arnold.AiNodeLookUpByName( "testPlane" )
			self.assertTrue( arnold.AiNodeEntryGetType( arnold.AiNodeGetNodeEntry( n ) ), arnold.AI_NODE_SHAPE )

	def testRenderRegion( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.camera(
			"testCamera",
			IECoreScene.Camera(
				parameters = {
					"resolution" : imath.V2i( 2000, 1000 ),
					"renderRegion" : imath.Box2i( imath.V2i( 0 ), imath.V2i( 1999, 749 ) ),
				}
			),
			r.attributes( IECore.CompoundObject() )
		)

		r.option( "camera", IECore.StringData( "testCamera" ) )

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			options = arnold.AiUniverseGetOptions()

			self.assertEqual( arnold.AiNodeGetInt( options, "xres" ), 2000 )
			self.assertEqual( arnold.AiNodeGetInt( options, "yres" ), 1000 )

			self.assertEqual( arnold.AiNodeGetInt( options, "region_min_x" ), 0 )
			self.assertEqual( arnold.AiNodeGetInt( options, "region_min_y" ), 0 )
			self.assertEqual( arnold.AiNodeGetInt( options, "region_max_x" ), 1999 )
			self.assertEqual( arnold.AiNodeGetInt( options, "region_max_y" ), 749 )

	def testShaderReuse( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		for i in range( 0, 10 ) :

			a = IECore.CompoundObject( {
				"ai:surface" : IECore.ObjectVector( [ IECoreScene.Shader( "flat" ) ] ),
			} )

			r.object(
				"testPlane%d" % i,
				IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
				# We keep specifying the same shader, but we'd like the renderer
				# to be frugal and reuse a single arnold shader on the other side.
				r.attributes( a )
			)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			self.assertEqual( len( self.__allNodes( type = arnold.AI_NODE_SHADER ) ), 1 )

	def testShaderGarbageCollection( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.Interactive,
		)

		r.output(
			"test",
			IECoreScene.Output(
				self.temporaryDirectory() + "/beauty.exr",
				"exr",
				"rgba",
				{
				}
			)
		)

		o = r.object(
			"testPlane",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject() )
		)

		# Replace the shader a few times.
		for shader in ( "utility", "flat", "standard_surface" ) :
			a = IECore.CompoundObject( {
				"ai:surface" : IECore.ObjectVector( [ IECoreScene.Shader( shader ) ] ),
			} )
			o.attributes( r.attributes( a ) )
			del a

		r.render()
		self.assertEqual( len( self.__allNodes( type = arnold.AI_NODE_SHADER ) ), 1 )

		del o
		del r

	def testShaderNames( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		shader1 = IECore.ObjectVector( [
			IECoreScene.Shader( "noise", parameters = { "__handle" : "myHandle" } ),
			IECoreScene.Shader( "flat", parameters = { "color" : "link:myHandle" } ),
		] )

		r.object(
			"testPlane1",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes(
				IECore.CompoundObject( {
					"ai:surface" : shader1
				} )
			)
		)

		shader2 = IECore.ObjectVector( [
			IECoreScene.Shader( "noise", parameters = { "__handle" : "myHandle" } ),
			IECoreScene.Shader( "standard_surface", parameters = { "base_color" : "link:myHandle" } ),
		] )

		r.object(
			"testPlane2",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes(
				IECore.CompoundObject( {
					"ai:surface" : shader2
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shaders = self.__allNodes( type = arnold.AI_NODE_SHADER )
			self.assertEqual( len( shaders ), 4 )
			shaderNames = [ arnold.AiNodeGetName( s ) for s in shaders ]
			self.assertEqual( len( shaderNames ), 4 )
			self.assertEqual( len( [ i for i in shaderNames if i.split(":")[-1] == "myHandle" ] ), 2 )

	def testShaderNodeConnectionType( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		scalarColorShader = IECore.ObjectVector( [
			IECoreScene.Shader( "image", parameters = { "__handle" : "scalarColorSource" } ),
			IECoreScene.Shader( "lambert", parameters = { "Kd_color" : "link:scalarColorSource", "__handle" : "scalarColorTarget" } ),
		] )

		# Note that a persp_camera is not at all legitimate to put in a shader vector,
		# but it has a non-vector parameter of type NODE, so it works to test this functionality
		scalarNodeShader = IECore.ObjectVector( [
			IECoreScene.Shader( "gobo", parameters = { "__handle" : "scalarNodeSource" } ),
			IECoreScene.Shader( "persp_camera", parameters = { "filtermap" : "link:scalarNodeSource", "__handle" : "scalarNodeTarget" } ),
		] )

		# Omitting vector color test because there are no nodes included with Arnold which use this,
		# and we don't want a htoa dependency
		#vectorColorShader = IECore.ObjectVector( [
		#	IECore.Shader( "image", parameters = { "__handle" : "vectorColorSource" } ),
		#	IECore.Shader( "htoa__ramp_rgb", parameters = { "color" : IECore.StringVectorData(["link:vectorColorSource"]), "__handle" : "vectorColorTarget" } ),
		#] )

		vectorNodeShader = IECore.ObjectVector( [
			IECoreScene.Shader( "gobo", parameters = { "__handle" : "vectorNodeSource" } ),
			IECoreScene.Shader( "spot_light", parameters = { "filters" : IECore.StringVectorData(["link:vectorNodeSource"]), "__handle" : "vectorNodeTarget" } ),
		] )

		for name,s in [ ( "scalarColor", scalarColorShader ), ( "scalarNode", scalarNodeShader ), ( "vectorNode", vectorNodeShader ) ]:
			r.object(
				"testPlane_%s" % name,
				IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
				r.attributes(
					IECore.CompoundObject( {
						"ai:surface" : s
					} )
				)
			)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :
			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			target = arnold.AtNode.from_address( arnold.AiNodeGetPtr( arnold.AiNodeLookUpByName( "testPlane_scalarColor" ), "shader" ) )
			source = arnold.AiNodeGetLink( target, "Kd_color" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( source ) ), "image" )

			target = arnold.AtNode.from_address( arnold.AiNodeGetPtr( arnold.AiNodeLookUpByName( "testPlane_scalarNode" ), "shader" ) )
			sourcePtr = arnold.AiNodeGetPtr( target, "filtermap" )
			source = arnold.AtNode.from_address( sourcePtr )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( source ) ), "gobo" )

			#target = arnold.AtNode.from_address( arnold.AiNodeGetPtr( arnold.AiNodeLookUpByName( "testPlane_vectorColor" ), "shader" ) )
			#source = arnold.AiNodeGetLink( target, "color[0]" )
			#self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( source ) ), "image" )

			target = arnold.AtNode.from_address( arnold.AiNodeGetPtr( arnold.AiNodeLookUpByName( "testPlane_vectorNode" ), "shader" ) )
			sourcePtr = arnold.AiNodeGetPtr( target, "filters" )
			source = arnold.AtNode.from_address( sourcePtr )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( source ) ), "gobo" )

	def testLightNames( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		lightShader = IECore.ObjectVector( [ IECoreScene.Shader( "point_light", "ai:light" ), ] )
		r.light(
			"testLight",
			None,
			r.attributes(
				IECore.CompoundObject( {
					"ai:light" : lightShader
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			lights = self.__allNodes( type = arnold.AI_NODE_LIGHT )
			self.assertEqual( len( lights ), 1 )
			self.assertEqual( "light:testLight", arnold.AiNodeGetName( lights[0] ) )

	def testLightTransforms( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		lightAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:light" : IECore.ObjectVector( [ IECoreScene.Shader( "point_light", "ai:light" ), ] )
			} )
		)

		r.light( "untransformedLight", None, lightAttributes )

		staticLight = r.light( "staticLight", None, lightAttributes )
		staticLight.transform( imath.M44f().translate( imath.V3f( 1, 2, 3 ) ) )

		movingLight = r.light( "movingLight", None, lightAttributes )
		movingLight.transform(
			[ imath.M44f().translate( imath.V3f( 1, 2, 3 ) ), imath.M44f().translate( imath.V3f( 4, 5, 6 ) ) ],
			[ 2.5, 3.5 ]
		)

		del lightAttributes, staticLight, movingLight
		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			untransformedLight = arnold.AiNodeLookUpByName( "light:untransformedLight" )
			staticLight = arnold.AiNodeLookUpByName( "light:staticLight" )
			movingLight = arnold.AiNodeLookUpByName( "light:movingLight" )

			m = arnold.AiNodeGetMatrix( untransformedLight, "matrix" )
			self.assertEqual( self.__m44f( m ), imath.M44f() )

			m = arnold.AiNodeGetMatrix( staticLight, "matrix" )
			self.assertEqual( self.__m44f( m ), imath.M44f().translate( imath.V3f( 1, 2, 3 ) ) )

			self.assertEqual( arnold.AiNodeGetFlt( movingLight, "motion_start" ), 2.5 )
			self.assertEqual( arnold.AiNodeGetFlt( movingLight, "motion_end" ), 3.5 )

			matrices = arnold.AiNodeGetArray( movingLight, "matrix" )

			m = arnold.AiArrayGetMtx( matrices, 0 )
			self.assertEqual( self.__m44f( m ), imath.M44f().translate( imath.V3f( 1, 2, 3 ) ) )
			m = arnold.AiArrayGetMtx( matrices, 1 )
			self.assertEqual( self.__m44f( m ), imath.M44f().translate( imath.V3f( 4, 5, 6 ) ) )

	def testSharedLightAttributes( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		lightShader = IECore.ObjectVector( [ IECoreScene.Shader( "point_light", "ai:light" ), ] )
		lightAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:light" : lightShader
			} )
		)

		r.light( "testLight1", None, lightAttributes )
		r.light( "testLight2", None, lightAttributes )

		del lightAttributes
		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			lights = self.__allNodes( type = arnold.AI_NODE_LIGHT )
			self.assertEqual( len( lights ), 2 )
			self.assertEqual( set( [ arnold.AiNodeGetName( l ) for l in lights ] ), { "light:testLight1", "light:testLight2" } )

	def testAttributes( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.object(
			"testMesh1",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( {
				"doubleSided" : IECore.BoolData( True ),
				"ai:visibility:camera" : IECore.BoolData( False ),
				"ai:visibility:shadow" : IECore.BoolData( True ),
				"ai:visibility:diffuse_reflect" : IECore.BoolData( False ),
				"ai:visibility:specular_reflect" : IECore.BoolData( True ),
				"ai:visibility:diffuse_transmit" : IECore.BoolData( False ),
				"ai:visibility:specular_transmit" : IECore.BoolData( True ),
				"ai:visibility:volume" : IECore.BoolData( False ),
				"ai:visibility:subsurface" : IECore.BoolData( True ),
				"ai:receive_shadows" : IECore.BoolData( True ),
				"ai:self_shadows" : IECore.BoolData( True ),
				"ai:matte" : IECore.BoolData( True ),
				"ai:opaque" : IECore.BoolData( True ),
			} ) ),
		)

		r.object(
			"testMesh2",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( {
				"doubleSided" : IECore.BoolData( False ),
				"ai:visibility:camera" : IECore.BoolData( True ),
				"ai:visibility:shadow" : IECore.BoolData( False ),
				"ai:visibility:diffuse_reflect" : IECore.BoolData( True ),
				"ai:visibility:specular_reflect" : IECore.BoolData( False ),
				"ai:visibility:diffuse_transmit" : IECore.BoolData( True ),
				"ai:visibility:specular_transmit" : IECore.BoolData( False ),
				"ai:visibility:volume" : IECore.BoolData( True ),
				"ai:visibility:subsurface" : IECore.BoolData( False ),
				"ai:receive_shadows" : IECore.BoolData( False ),
				"ai:self_shadows" : IECore.BoolData( False ),
				"ai:matte" : IECore.BoolData( False ),
				"ai:opaque" : IECore.BoolData( False ),
			} ) ),
		)

		r.object(
			"testMesh3",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject() ),
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			o1 = arnold.AiNodeLookUpByName( "testMesh1" )
			o2 = arnold.AiNodeLookUpByName( "testMesh2" )
			o3 = arnold.AiNodeLookUpByName( "testMesh3" )

			self.assertEqual( arnold.AiNodeGetByte( o1, "sidedness" ), arnold.AI_RAY_ALL )
			self.assertEqual( arnold.AiNodeGetByte( o2, "sidedness" ), arnold.AI_RAY_UNDEFINED )
			self.assertEqual( arnold.AiNodeGetByte( o3, "sidedness" ), arnold.AI_RAY_ALL )

			self.assertEqual(
				arnold.AiNodeGetByte( o1, "visibility" ),
				arnold.AI_RAY_ALL & ~( arnold.AI_RAY_CAMERA | arnold.AI_RAY_DIFFUSE_TRANSMIT | arnold.AI_RAY_DIFFUSE_REFLECT | arnold.AI_RAY_VOLUME )
			)
			self.assertEqual(
				arnold.AiNodeGetByte( o2, "visibility" ),
				arnold.AI_RAY_ALL & ~( arnold.AI_RAY_SHADOW | arnold.AI_RAY_SPECULAR_TRANSMIT | arnold.AI_RAY_SPECULAR_REFLECT | arnold.AI_RAY_SUBSURFACE )
			)
			self.assertEqual(
				arnold.AiNodeGetByte( o3, "visibility" ),
				arnold.AI_RAY_ALL
			)

			for p in ( "receive_shadows", "self_shadows", "matte", "opaque" ) :
				self.assertEqual( arnold.AiNodeGetBool( o1, p ), True )
				self.assertEqual( arnold.AiNodeGetBool( o2, p ), False )
				self.assertEqual( arnold.AiNodeGetBool( o3, p ), p != "matte" )

	def testOutputs( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.output(
			"testA",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"color A",
				{}
			)
		)

		# NOTE : includeAlpha is currently undocumented, and we have not yet decided exactly how
		# to generalize it across renderer backends, so it may change in the future.
		r.output(
			"testB",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"color B",
				{
					"includeAlpha" : True,
				}
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			options = arnold.AiUniverseGetOptions()
			outputs = arnold.AiNodeGetArray( options, "outputs" )
			self.assertEqual( arnold.AiArrayGetNumElements( outputs ), 2 )
			outputSet = set( [ arnold.AiArrayGetStr( outputs, 0 ), arnold.AiArrayGetStr( outputs, 1 ) ] )
			self.assertEqual( outputSet, set( [
				"A RGB ieCoreArnold:filter:testA ieCoreArnold:display:testA",
				"B RGBA ieCoreArnold:filter:testB ieCoreArnold:display:testB"
			] ) )

	def testOutputFilters( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.output(
			"test",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"rgba",
				{
					"filter" : "gaussian",
					"filterwidth" : imath.V2f( 3.5 ),
				}
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			filters = self.__allNodes( type = arnold.AI_NODE_FILTER )
			self.assertEqual( len( filters ), 1 )
			f = filters[0]

			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( f ) ), "gaussian_filter" )
			self.assertEqual( arnold.AiNodeGetFlt( f, "width" ), 3.5 )

	def testOutputLPEs( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.output(
			"test",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"lpe C.*D.*",
				{}
			)
		)

		r.output(
			"testWithAlpha",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"lpe C.*D.*",
				{
					"includeAlpha" : True,
				}
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			options = arnold.AiUniverseGetOptions()
			outputs = arnold.AiNodeGetArray( options, "outputs" )
			self.assertEqual( arnold.AiArrayGetNumElements( outputs ), 2 )
			outputSet = set( [ arnold.AiArrayGetStr( outputs, 0 ), arnold.AiArrayGetStr( outputs, 1 ) ] )
			self.assertEqual( outputSet, set( [
				"ieCoreArnold:lpe:test RGB ieCoreArnold:filter:test ieCoreArnold:display:test",
				"ieCoreArnold:lpe:testWithAlpha RGBA ieCoreArnold:filter:testWithAlpha ieCoreArnold:display:testWithAlpha"
			] ) )

			lpes = arnold.AiNodeGetArray( options, "light_path_expressions" )
			self.assertEqual( arnold.AiArrayGetNumElements( lpes ), 2 )
			lpeSet = set( [ arnold.AiArrayGetStr( lpes, 0 ), arnold.AiArrayGetStr( lpes, 1 ) ] )
			self.assertEqual( lpeSet, set( [
				"ieCoreArnold:lpe:test C.*D.*",
				"ieCoreArnold:lpe:testWithAlpha C.*D.*"
			] ) )

	def testExrMetadata( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.output(
			"exrTest",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"rgba",
				{
					"filter" : "gaussian",
					"filterwidth" : imath.V2f( 3.5 ),
					"custom_attributes" : IECore.StringVectorData([ "string 'original data' test" ]),
					"header:bar" : IECore.BoolData( True ),
				}
			)
		)

		r.output(
			"exrDataTest",
			IECoreScene.Output(
				"beauty.exr",
				"exr",
				"rgba",
				{
					"filter" : "gaussian",
					"filterwidth" : imath.V2f( 3.5 ),
					"header:foo" : IECore.StringData( "bar" ),
					"header:bar" : IECore.BoolData( True ),
					"header:nobar" : IECore.BoolData( False ),
					"header:floatbar" : IECore.FloatData( 1.618034 ),
					"header:intbar" : IECore.IntData( 42 ),
					"header:vec2i" : IECore.V2iData( imath.V2i( 100 ) ),
					"header:vec3i" : IECore.V3iData( imath.V3i( 100 ) ),
					"header:vec2f" : IECore.V2fData( imath.V2f( 100 ) ),
					"header:vec3f" : IECore.V3fData( imath.V3f( 100 ) ),
					"header:color3f" : IECore.Color3fData( imath.Color3f( 100 ) ),
					"header:color4f" : IECore.Color4fData( imath.Color4f( 100 ) ),
				}
			)
		)

		msg = IECore.CapturingMessageHandler()
		with msg:
			r.output(
				"tiffTest",
				IECoreScene.Output(
					"beauty.tiff",
					"tiff",
					"rgba",
					{
						"filter" : "gaussian",
						"filterwidth" : imath.V2f( 3.5 ),
						"header:foo" : IECore.StringData( "bar" ),
						"header:bar" : IECore.StringVectorData([ 'one', 'two', 'three' ])  # not supported and should print a warning
					}
				)
			)

		r.render()
		del r

		expectedMessage = 'Cannot convert data "bar" of type "StringVectorData".'

		self.assertEqual( len(msg.messages), 1 )
		self.assertEqual( msg.messages[-1].message, expectedMessage )
		self.assertEqual( msg.messages[-1].level, IECore.Msg.Level.Warning)

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			# test if data was added correctly to existing data
			exrDriver = arnold.AiNodeLookUpByName( "ieCoreArnold:display:exrTest" )
			customAttributes = arnold.AiNodeGetArray( exrDriver, "custom_attributes" )
			customAttributesValues = set([ arnold.AiArrayGetStr( customAttributes, i ) for i in range( arnold.AiArrayGetNumElements( customAttributes.contents ) ) ])
			customAttributesExpected = set([
				"int 'bar' 1",
				"string 'original data' test"])

			self.assertEqual( customAttributesValues, customAttributesExpected )

			# test if all data types work correctly
			exrDriver = arnold.AiNodeLookUpByName( "ieCoreArnold:display:exrDataTest" )
			customAttributes = arnold.AiNodeGetArray( exrDriver, "custom_attributes" )
			customAttributesValues = set([ arnold.AiArrayGetStr( customAttributes, i ) for i in range( arnold.AiArrayGetNumElements( customAttributes.contents ) ) ])

			customAttributesExpected = set([
				"string 'foo' bar",
				"int 'bar' 1",
				"int 'nobar' 0",
				"float 'floatbar' 1.618034",
				"int 'intbar' 42",
				"string 'vec2i' (100 100)",
				"string 'vec3i' (100 100 100)",
				"string 'vec2f' (100 100)",
				"string 'vec3f' (100 100 100)",
				"string 'color3f' (100 100 100)",
				"string 'color4f' (100 100 100 100)"])

			self.assertEqual( customAttributesValues, customAttributesExpected )

			# make sure that attribute isn't added to drivers that don't support it
			tiffDriver = arnold.AiNodeLookUpByName( "ieCoreArnold:display:tiffTest" )
			customAttributes = arnold.AiNodeGetArray( tiffDriver, "custom_attributes" )
			self.assertEqual(customAttributes, None)

	def testInstancing( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		polyPlane = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )
		subdivPlane = polyPlane.copy()
		subdivPlane.interpolation = "catmullClark"

		defaultAttributes = r.attributes( IECore.CompoundObject() )
		adaptiveAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:polymesh:subdiv_adaptive_error" : IECore.FloatData( 0.1 ),
			} )
		)
		nonAdaptiveAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:polymesh:subdiv_adaptive_error" : IECore.FloatData( 0 ),
			} )
		)
		adaptiveObjectSpaceAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:polymesh:subdiv_adaptive_error" : IECore.FloatData( 0.1 ),
				"ai:polymesh:subdiv_adaptive_space" : IECore.StringData( "object" ),
			} )
		)
		smoothDerivsTrueAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:polymesh:subdiv_smooth_derivs" : IECore.BoolData( True )
			} )
		)

		# We should be able to automatically instance polygon meshes
		# regardless of the subdivision settings, because they're
		# irrelevant.

		r.object( "polyDefaultAttributes1", polyPlane.copy(), defaultAttributes )
		r.object( "polyDefaultAttributes2", polyPlane.copy(), defaultAttributes )

		r.object( "polyAdaptiveAttributes1", polyPlane.copy(), adaptiveAttributes )
		r.object( "polyAdaptiveAttributes2", polyPlane.copy(), adaptiveAttributes )

		# And we should be able to instance subdiv meshes with
		# non-adaptive subdivision.

		r.object( "subdivDefaultAttributes1", subdivPlane.copy(), defaultAttributes )
		r.object( "subdivDefaultAttributes2", subdivPlane.copy(), defaultAttributes )

		r.object( "subdivNonAdaptiveAttributes1", subdivPlane.copy(), nonAdaptiveAttributes )
		r.object( "subdivNonAdaptiveAttributes2", subdivPlane.copy(), nonAdaptiveAttributes )

		# But if adaptive subdivision is enabled, we can't, because the
		# mesh can't be subdivided appropriately for both instances.

		r.object( "subdivAdaptiveAttributes1", subdivPlane.copy(), adaptiveAttributes )
		r.object( "subdivAdaptiveAttributes2", subdivPlane.copy(), adaptiveAttributes )

		# Although we should be able to if the adaptive space is "object".

		r.object( "subdivAdaptiveObjectSpaceAttributes1", subdivPlane.copy(), adaptiveObjectSpaceAttributes )
		r.object( "subdivAdaptiveObjectSpaceAttributes2", subdivPlane.copy(), adaptiveObjectSpaceAttributes )

		# If smooth derivatives are required, that'll require creating a separate polymesh and an instance of it

		r.object( "subdivSmoothDerivsAttributes1", subdivPlane.copy(), smoothDerivsTrueAttributes )

		r.render()
		del defaultAttributes, adaptiveAttributes, nonAdaptiveAttributes, adaptiveObjectSpaceAttributes
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			numInstances = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "ginstance" ] )
			numPolyMeshes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "polymesh" ] )

			self.assertEqual( numPolyMeshes, 6 )
			self.assertEqual( numInstances, 11 )

			self.__assertInstanced(
				"polyDefaultAttributes1",
				"polyDefaultAttributes2",
				"polyAdaptiveAttributes1",
				"polyAdaptiveAttributes2",
			)

			self.__assertInstanced(
				"subdivDefaultAttributes1",
				"subdivDefaultAttributes2",
				"subdivNonAdaptiveAttributes1",
				"subdivNonAdaptiveAttributes2",
			)

			self.__assertNotInstanced(
				"subdivAdaptiveAttributes1",
				"subdivAdaptiveAttributes2"
			)

			self.__assertInstanced(
				"subdivAdaptiveObjectSpaceAttributes1",
				"subdivAdaptiveObjectSpaceAttributes2",
			)

	def testTransformTypeAttribute( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		plane = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )

		r.object(
			"planeDefault",
			plane,
			r.attributes( IECore.CompoundObject() )
		)
		r.object(
			"planeLinear",
			plane,
			r.attributes(
				IECore.CompoundObject( {
					"ai:transform_type" : IECore.StringData( "linear" ),
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			defaultNode = arnold.AiNodeLookUpByName( "planeDefault" )
			linearNode = arnold.AiNodeLookUpByName( "planeLinear" )
			self.assertEqual( arnold.AiNodeGetStr( defaultNode, "transform_type" ), "rotate_about_center" )
			self.assertEqual( arnold.AiNodeGetStr( linearNode, "transform_type" ), "linear" )

	def testSubdivisionAttributes( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		subdivPlane = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )
		subdivPlane.interpolation = "catmullClark"

		r.object(
			"plane",
			subdivPlane,
			r.attributes(
				IECore.CompoundObject( {
					"ai:polymesh:subdiv_iterations" : IECore.IntData( 10 ),
					"ai:polymesh:subdiv_adaptive_error" : IECore.FloatData( 0.25 ),
					"ai:polymesh:subdiv_adaptive_metric" : IECore.StringData( "edge_length" ),
					"ai:polymesh:subdiv_adaptive_space" : IECore.StringData( "raster" ),
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			node = arnold.AiNodeLookUpByName( "plane" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( node ) ), "polymesh" )
			self.assertEqual( arnold.AiNodeGetByte( node, "subdiv_iterations" ), 10 )
			self.assertEqual( arnold.AiNodeGetFlt( node, "subdiv_adaptive_error" ), 0.25 )
			self.assertEqual( arnold.AiNodeGetStr( node, "subdiv_adaptive_metric" ), "edge_length" )
			self.assertEqual( arnold.AiNodeGetStr( node, "subdiv_adaptive_space" ), "raster" )

	def testSSSSetNameAttribute( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		plane = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )

		r.object(
			"plane",
			plane,
			r.attributes(
				IECore.CompoundObject( {
					"ai:sss_setname" : IECore.StringData( "testSet" ),
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			node = arnold.AiNodeLookUpByName( "plane" )
			self.assertEqual( arnold.AiNodeGetStr( node, "sss_setname" ), "testSet" )

	def testUserAttributes( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.object(
			"plane1",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes(
				IECore.CompoundObject( {
					"user:testInt" : IECore.IntData( 1 ),
					"user:testFloat" : IECore.FloatData( 2.5 ),
					"user:testV3f" : IECore.V3fData( imath.V3f( 1, 2, 3 ) ),
					"user:testColor3f" : IECore.Color3fData( imath.Color3f( 4, 5, 6 ) ),
					"user:testString" : IECore.StringData( "we're all doomed" ),
				} )
			)
		)

		r.object(
			"plane2",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes(
				IECore.CompoundObject( {
					"user:testInt" : IECore.IntData( 2 ),
					"user:testFloat" : IECore.FloatData( 25 ),
					"user:testV3f" : IECore.V3fData( imath.V3f( 0, 1, 0 ) ),
					"user:testColor3f" : IECore.Color3fData( imath.Color3f( 1, 0.5, 0 ) ),
					"user:testString" : IECore.StringData( "indeed" ),
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			plane1 = arnold.AiNodeLookUpByName( "plane1" )
			self.assertEqual( arnold.AiNodeGetInt( plane1, "user:testInt" ), 1 )
			self.assertEqual( arnold.AiNodeGetFlt( plane1, "user:testFloat" ), 2.5 )
			self.assertEqual( arnold.AiNodeGetVec( plane1, "user:testV3f" ), arnold.AtVector( 1, 2, 3 ) )
			self.assertEqual( arnold.AiNodeGetRGB( plane1, "user:testColor3f" ), arnold.AtRGB( 4, 5, 6 ) )
			self.assertEqual( arnold.AiNodeGetStr( plane1, "user:testString" ), "we're all doomed" )

			plane2 = arnold.AiNodeLookUpByName( "plane2" )
			self.assertEqual( arnold.AiNodeGetInt( plane2, "user:testInt" ), 2 )
			self.assertEqual( arnold.AiNodeGetFlt( plane2, "user:testFloat" ), 25 )
			self.assertEqual( arnold.AiNodeGetVec( plane2, "user:testV3f" ), arnold.AtVector( 0, 1, 0 ) )
			self.assertEqual( arnold.AiNodeGetRGB( plane2, "user:testColor3f" ), arnold.AtRGB( 1, 0.5, 0 ) )
			self.assertEqual( arnold.AiNodeGetStr( plane2, "user:testString" ), "indeed" )

	def testDisplacementAttributes( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		plane = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )
		noise = IECore.ObjectVector( [ IECoreScene.Shader( "noise", "ai:displacement", {} ) ] )

		sharedAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:disp_map" : noise,
				"ai:disp_height" : IECore.FloatData( 0.25 ),
				"ai:disp_padding" : IECore.FloatData( 2.5 ),
				"ai:disp_zero_value" : IECore.FloatData( 0.5 ),
				"ai:disp_autobump" : IECore.BoolData( True ),
			} )
		)

		r.object( "plane1", plane, sharedAttributes )
		r.object( "plane2", plane, sharedAttributes )
		del sharedAttributes

		r.object(
			"plane3",
			plane,
			r.attributes(
				IECore.CompoundObject( {
					"ai:disp_map" : noise,
					"ai:disp_height" : IECore.FloatData( 0.5 ),
					"ai:disp_padding" : IECore.FloatData( 5.0 ),
					"ai:disp_zero_value" : IECore.FloatData( 0.0 ),
					"ai:disp_autobump" : IECore.BoolData( True ),
				} )
			)
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			self.assertEqual( len( shapes ), 5 )

			plane1 = arnold.AiNodeLookUpByName( "plane1" )
			plane2 = arnold.AiNodeLookUpByName( "plane2" )
			plane3 = arnold.AiNodeLookUpByName( "plane3" )

			self.assertTrue( arnold.AiNodeIs( plane1, "ginstance" ) )
			self.assertTrue( arnold.AiNodeIs( plane2, "ginstance" ) )
			self.assertTrue( arnold.AiNodeIs( plane3, "ginstance" ) )

			self.assertEqual( arnold.AiNodeGetPtr( plane1, "node" ), arnold.AiNodeGetPtr( plane2, "node" ) )
			self.assertNotEqual( arnold.AiNodeGetPtr( plane2, "node" ), arnold.AiNodeGetPtr( plane3, "node" ) )

			polymesh1 = arnold.AtNode.from_address( arnold.AiNodeGetPtr( plane1, "node" ) )
			polymesh2 = arnold.AtNode.from_address( arnold.AiNodeGetPtr( plane3, "node" ) )

			self.assertTrue( arnold.AiNodeIs( polymesh1, "polymesh" ) )
			self.assertTrue( arnold.AiNodeIs( polymesh2, "polymesh" ) )

			self.assertEqual( arnold.AiNodeGetPtr( polymesh1, "disp_map" ), arnold.AiNodeGetPtr( polymesh2, "disp_map" ) )
			self.assertEqual( arnold.AiNodeGetFlt( polymesh1, "disp_height" ), 0.25 )
			self.assertEqual( arnold.AiNodeGetFlt( polymesh2, "disp_height" ), 0.5 )
			self.assertEqual( arnold.AiNodeGetFlt( polymesh1, "disp_padding" ), 2.5 )
			self.assertEqual( arnold.AiNodeGetFlt( polymesh2, "disp_padding" ), 5.0 )
			self.assertEqual( arnold.AiNodeGetFlt( polymesh1, "disp_zero_value" ), 0.5 )
			self.assertEqual( arnold.AiNodeGetFlt( polymesh2, "disp_zero_value" ), 0.0 )
			self.assertEqual( arnold.AiNodeGetBool( polymesh1, "disp_autobump" ), True )
			self.assertEqual( arnold.AiNodeGetBool( polymesh2, "disp_autobump" ), True )

	def testSubdividePolygonsAttribute( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		meshes = {}
		meshes["linear"] = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )
		meshes["catmullClark"] = meshes["linear"].copy()
		meshes["catmullClark"].interpolation = "catmullClark"

		attributes = {}
		for subdividePolygons in ( None, False, True ) :
			a = IECore.CompoundObject()
			if subdividePolygons is not None :
				a["ai:polymesh:subdivide_polygons"] = IECore.BoolData( subdividePolygons )
			attributes[subdividePolygons] = r.attributes( a )

		for interpolation in meshes.keys() :
			for subdividePolygons in attributes.keys() :
				r.object( interpolation + "-" + str( subdividePolygons ), meshes[interpolation], attributes[subdividePolygons] )

		del attributes

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			for interpolation in meshes.keys() :
				for subdividePolygons in ( None, False, True ) :

					instance = arnold.AiNodeLookUpByName( interpolation + "-" + str( subdividePolygons ) )
					self.assertTrue( arnold.AiNodeIs( instance, "ginstance" ) )

					mesh = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )
					self.assertTrue( arnold.AiNodeIs( mesh, "polymesh" ) )

					if subdividePolygons and interpolation == "linear" :
						self.assertEqual( arnold.AiNodeGetStr( mesh, "subdiv_type" ), "linear" )
					else :
						self.assertEqual( arnold.AiNodeGetStr( mesh, "subdiv_type" ), "catclark" if interpolation == "catmullClark" else "none" )

	def testUVSmoothingAttribute( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		mesh = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )
		mesh.interpolation = "catmullClark"

		smoothingTypes = ( "pin_corners", "pin_borders", "linear", "smooth", None )
		for uvSmoothing in smoothingTypes :
			attributes = IECore.CompoundObject()
			if uvSmoothing is not None :
				attributes["ai:polymesh:subdiv_uv_smoothing"] = IECore.StringData( uvSmoothing )
			r.object(
				"mesh-" + ( uvSmoothing or "default" ),
				mesh,
				r.attributes( attributes )
			)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			for uvSmoothing in smoothingTypes :

				instance = arnold.AiNodeLookUpByName( "mesh-" + ( uvSmoothing or "default" ) )
				self.assertTrue( arnold.AiNodeIs( instance, "ginstance" ) )

				mesh = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )
				self.assertTrue( arnold.AiNodeIs( mesh, "polymesh" ) )

				self.assertEqual( arnold.AiNodeGetStr( mesh, "subdiv_uv_smoothing" ), uvSmoothing or "pin_corners" )

	def testMeshLight( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		l = r.light(
			"myLight",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes(
				IECore.CompoundObject( {
					"ai:light" : IECore.ObjectVector( [ IECoreScene.Shader( "mesh_light", "ai:light" ), ] )
				} )
			)
		)
		del l

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			self.assertEqual( len( shapes ), 2 )

			instance = arnold.AiNodeLookUpByName( "myLight" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( instance ) ), "ginstance" )
			mesh = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( mesh ) ), "polymesh" )

			lights = self.__allNodes( type = arnold.AI_NODE_LIGHT )
			self.assertEqual( len( lights ), 1 )
			light = lights[0]
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( light ) ), "mesh_light" )
			self.assertEqual( arnold.AiNodeGetPtr( light, "mesh" ), ctypes.addressof( instance.contents ) )

	def testMeshLightsWithSharedShaders( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		lightShaderNetwork = IECore.ObjectVector( [
			IECoreScene.Shader( "flat", "ai:shader", { "__handle" : "colorHandle" } ),
			IECoreScene.Shader( "mesh_light", "ai:light", { "color" : "link:colorHandle" } ),
		] )

		l1 = r.light(
			"myLight1",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( {
				"ai:light" : lightShaderNetwork,
			} ) )
		)
		del l1

		l2 = r.light(
			"myLight2",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( {
				"ai:light" : lightShaderNetwork,
			} ) )
		)
		del l2

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			self.assertEqual( len( shapes ), 3 )

			instance1 = arnold.AiNodeLookUpByName( "myLight1" )
			instance2 = arnold.AiNodeLookUpByName( "myLight2" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( instance1 ) ), "ginstance" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( instance2 ) ), "ginstance" )

			self.assertEqual( arnold.AiNodeGetPtr( instance1, "node" ), arnold.AiNodeGetPtr( instance2, "node" ) )

			mesh = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance1, "node" ) )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( mesh ) ), "polymesh" )

			lights = self.__allNodes( type = arnold.AI_NODE_LIGHT )
			self.assertEqual( len( lights ), 2 )

			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( lights[0] ) ), "mesh_light" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( lights[1] ) ), "mesh_light" )

			flat1 = arnold.AiNodeGetLink( lights[0], "color" )
			flat2 = arnold.AiNodeGetLink( lights[1], "color" )

			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( flat1 ) ), "flat" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( flat2 ) ), "flat" )

	def testOSLShaders( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		network = IECore.ObjectVector( [
			IECoreScene.Shader(
				"Pattern/Noise",
				"osl:shader",
				{
					"scale" : 10.0,
					"__handle" : "noiseHandle"
				}
			),
			IECoreScene.Shader(
				"Pattern/ColorSpline",
				"osl:shader",
				{
					"spline" : IECore.SplinefColor3f(
						IECore.CubicBasisf.bSpline(),
						[
							( 0, imath.Color3f( 0.25 ) ),
							( 0, imath.Color3f( 0.25 ) ),
							( 1, imath.Color3f( 0.5 ) ),
							( 1, imath.Color3f( 0.5 ) ),
						]
					),
					"__handle" : "splineHandle"
				}
			),
			IECoreScene.Shader(
				"add",
				"ai:surface",
				{
					"input1" : "link:splineHandle",
					"input2" : "link:noiseHandle"
				}
			)
		] )

		o = r.object(
			"testPlane",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( { "ai:surface" : network } ) )
		)
		del o

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			options = arnold.AiUniverseGetOptions()
			self.assertTrue( os.path.expandvars( "$GAFFER_ROOT/shaders" ) in arnold.AiNodeGetStr( options, "plugin_searchpath" ) )

			n = arnold.AiNodeLookUpByName( "testPlane" )

			add = arnold.AtNode.from_address( arnold.AiNodeGetPtr( n, "shader" ) )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( add ) ), "add" )

			spline = arnold.AiNodeGetLink( add, "input1" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( spline ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( spline, "shadername" ), "Pattern/ColorSpline" )
			self.assertEqual( arnold.AiNodeGetStr( spline, "param_splineBasis" ), "bspline" )

			splinePositions = arnold.AiNodeGetArray( spline, "param_splinePositions" )
			self.assertEqual( arnold.AiArrayGetFlt( splinePositions, 0 ), 0 )
			self.assertEqual( arnold.AiArrayGetFlt( splinePositions, 1 ), 0 )
			self.assertEqual( arnold.AiArrayGetFlt( splinePositions, 2 ), 1 )
			self.assertEqual( arnold.AiArrayGetFlt( splinePositions, 3 ), 1 )

			splineValues = arnold.AiNodeGetArray( spline, "param_splineValues" )
			self.assertEqual( arnold.AiArrayGetRGB( splineValues, 0 ), arnold.AtRGB( 0.25, 0.25, 0.25 ) )
			self.assertEqual( arnold.AiArrayGetRGB( splineValues, 1 ), arnold.AtRGB( 0.25, 0.25, 0.25 ) )
			self.assertEqual( arnold.AiArrayGetRGB( splineValues, 2 ), arnold.AtRGB( 0.5, 0.5, 0.5 ) )
			self.assertEqual( arnold.AiArrayGetRGB( splineValues, 3 ), arnold.AtRGB( 0.5, 0.5, 0.5 ) )

			noise = arnold.AiNodeGetLink( add, "input2" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( noise ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( noise, "shadername" ), "Pattern/Noise" )
			self.assertEqual( arnold.AiNodeGetFlt( noise, "param_scale" ), 10.0 )

	def testPureOSLShaders( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		network = IECore.ObjectVector( [ IECoreScene.Shader( "Pattern/Noise", "osl:shader" ) ] )

		o = r.object(
			"testPlane",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( { "osl:shader" : network } ) )
		)
		del o

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			options = arnold.AiUniverseGetOptions()

			n = arnold.AiNodeLookUpByName( "testPlane" )

			noise = arnold.AtNode.from_address( arnold.AiNodeGetPtr( n, "shader" ) )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( noise ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( noise, "shadername" ), "Pattern/Noise" )

	def testOSLMultipleOutputs( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		network = IECore.ObjectVector( [
			IECoreScene.Shader(
				"Conversion/ColorToFloat",
				"osl:shader",
				{
					"c" : imath.Color3f( 0.1, 0.2, 0.3 ),
					"__handle" : "colorToFloatHandle"
				}
			),
			IECoreScene.Shader(
				"Conversion/FloatToColor",
				"osl:shader",
				{
					"r" : "link:colorToFloatHandle.r",
					"g" : "link:colorToFloatHandle.g",
					"b" : "link:colorToFloatHandle.b",
				}
			)
		] )

		r.object(
			"testPlane",
			IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			r.attributes( IECore.CompoundObject( { "ai:surface" : network } ) )
		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :
			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			n = arnold.AiNodeLookUpByName( "testPlane" )

			floatToColor = arnold.AtNode.from_address( arnold.AiNodeGetPtr( n, "shader" ) )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( floatToColor ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( floatToColor, "shadername" ), "Conversion/FloatToColor" )

			colorToFloatR = arnold.AiNodeGetLink( floatToColor, "param_r" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( colorToFloatR ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( colorToFloatR, "output" ), "r" )
			self.assertEqual( arnold.AiNodeGetStr( colorToFloatR, "shadername" ), "Conversion/ColorToFloat" )
			self.assertEqual( arnold.AiNodeGetRGB( colorToFloatR, "param_c" ),  arnold.AtRGB( 0.1, 0.2, 0.3 ))

			colorToFloatG = arnold.AiNodeGetLink( floatToColor, "param_g" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( colorToFloatG ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( colorToFloatG, "output" ), "g" )
			self.assertEqual( arnold.AiNodeGetStr( colorToFloatG, "shadername" ), "Conversion/ColorToFloat" )
			self.assertEqual( arnold.AiNodeGetRGB( colorToFloatG, "param_c" ),  arnold.AtRGB( 0.1, 0.2, 0.3 ))

			colorToFloatB = arnold.AiNodeGetLink( floatToColor, "param_b" )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( colorToFloatB ) ), "osl" )
			self.assertEqual( arnold.AiNodeGetStr( colorToFloatB, "output" ), "b" )
			self.assertEqual( arnold.AiNodeGetStr( colorToFloatB, "shadername" ), "Conversion/ColorToFloat" )
			self.assertEqual( arnold.AiNodeGetRGB( colorToFloatB, "param_c" ),  arnold.AtRGB( 0.1, 0.2, 0.3 ))

	def testTraceSets( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		objectNamesAndSets = [
			( "crimsonSphere", IECore.InternedStringVectorData( [ "roundThings", "redThings" ] ) ),
			( "emeraldBall", IECore.InternedStringVectorData( [ "roundThings", "greenThings" ] ) ),
			( "greenFrog", IECore.InternedStringVectorData( [ "livingThings", "greenThings" ] ) ),
			( "scarletPimpernel", IECore.InternedStringVectorData( [ "livingThings", "redThings" ] ) ),
			( "mysterious", IECore.InternedStringVectorData() ),
			( "evasive", None ),
		]

		for objectName, sets in objectNamesAndSets :

			attributes = IECore.CompoundObject()
			if sets is not None :
				attributes["sets"] = sets

			r.object(
				objectName,
				IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
				r.attributes( attributes ),
			)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			for objectName, sets in objectNamesAndSets :

				n = arnold.AiNodeLookUpByName( objectName )
				a = arnold.AiNodeGetArray( n, "trace_sets" )

				if sets is None or len( sets ) == 0 :
					sets = [ "__none__" ]

				self.assertEqual( arnold.AiArrayGetNumElements( a.contents ), len( sets ) )
				for i in range( 0, arnold.AiArrayGetNumElements( a.contents ) ) :
					self.assertEqual( arnold.AiArrayGetStr( a, i ), sets[i] )

	def testCurvesAttributes( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		curves = IECoreScene.CurvesPrimitive.createBox( imath.Box3f( imath.V3f( -1 ), imath.V3f( 1 ) ) )

		defaultAttributes = r.attributes( IECore.CompoundObject() )

		pixelWidth1Attributes = r.attributes(
			IECore.CompoundObject( {
				"ai:curves:min_pixel_width" : IECore.FloatData( 1 ),
			} )
		)

		pixelWidth2Attributes = r.attributes(
			IECore.CompoundObject( {
				"ai:curves:min_pixel_width" : IECore.FloatData( 2 ),
			} )
		)

		modeRibbonAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:curves:mode" : IECore.StringData( "ribbon" ),
			} )
		)

		modeThickAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:curves:mode" : IECore.StringData( "thick" ),
			} )
		)

		pixelWidth0ModeRibbonAttributes = r.attributes(
			IECore.CompoundObject( {
				"ai:curves:min_pixel_width" : IECore.FloatData( 0 ),
				"ai:curves:mode" : IECore.StringData( "ribbon" ),
			} )
		)

		r.object( "default", curves.copy(), defaultAttributes )
		r.object( "pixelWidth1", curves.copy(), pixelWidth1Attributes )
		r.object( "pixelWidth1Duplicate", curves.copy(), pixelWidth1Attributes )
		r.object( "pixelWidth2", curves.copy(), pixelWidth2Attributes )
		r.object( "modeRibbon", curves.copy(), modeRibbonAttributes )
		r.object( "modeThick", curves.copy(), modeThickAttributes )
		r.object( "pixelWidth0ModeRibbon", curves.copy(), pixelWidth0ModeRibbonAttributes )

		del defaultAttributes, pixelWidth1Attributes, pixelWidth2Attributes, modeRibbonAttributes, modeThickAttributes, pixelWidth0ModeRibbonAttributes

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			numInstances = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "ginstance" ] )
			numCurves = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "curves" ] )

			self.assertEqual( numInstances, 7 )
			self.assertEqual( numCurves, 4 )

			self.__assertInstanced(
				"default",
				"modeRibbon",
				"pixelWidth0ModeRibbon",
			)

			self.__assertInstanced(
				"pixelWidth1",
				"pixelWidth1Duplicate",
			)

			for name in ( "pixelWidth2", "modeRibbon", "modeThick" ) :
				self.__assertInstanced( name )

			for name, minPixelWidth, mode in (
				( "default", 0, "ribbon" ),
				( "pixelWidth1", 1, "ribbon" ),
				( "pixelWidth1Duplicate", 1, "ribbon" ),
				( "pixelWidth2", 2, "ribbon" ),
				( "modeRibbon", 0, "ribbon" ),
				( "modeThick", 0, "thick" ),
				( "pixelWidth0ModeRibbon", 0, "ribbon" ),
			) :

				instance = arnold.AiNodeLookUpByName( name )
				self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( instance ) ), "ginstance" )

				shape = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )
				self.assertEqual( arnold.AiNodeGetFlt( shape, "min_pixel_width" ), minPixelWidth )
				self.assertEqual( arnold.AiNodeGetStr( shape, "mode" ), mode )

	def testAttributeEditFailures( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.Interactive
		)

		polygonMesh = IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) )
		subdivMesh = polygonMesh.copy()
		subdivMesh.interpolation = "catmullClark"

		defaultAttributes = r.attributes( IECore.CompoundObject() )

		defaultIterationsAttributes = r.attributes( IECore.CompoundObject( {
			"ai:polymesh:subdiv_iterations" : IECore.IntData( 1 ),
		} ) )

		nonDefaultIterationsAttributes = r.attributes( IECore.CompoundObject( {
			"ai:polymesh:subdiv_iterations" : IECore.IntData( 2 ),
		} ) )

		subdividePolygonsAttributes = r.attributes( IECore.CompoundObject( {
			"ai:polymesh:subdivide_polygons" : IECore.BoolData( True )
		} ) )

		# Polygon mesh
		##############

		# No-op attribute edit should succeed.

		polygonMeshObject = r.object( "polygonMesh", polygonMesh, defaultAttributes )
		self.assertTrue( polygonMeshObject.attributes( defaultAttributes ) )
		self.assertTrue( polygonMeshObject.attributes( defaultIterationsAttributes ) )

		# Changing subdiv iterations should succeed, because it
		# doesn't apply to polygon meshes.

		self.assertTrue( polygonMeshObject.attributes( nonDefaultIterationsAttributes ) )
		self.assertTrue( polygonMeshObject.attributes( defaultAttributes ) )

		# But turning on subdivide polygons should fail, because then
		# we have changed the geometry.

		self.assertFalse( polygonMeshObject.attributes( subdividePolygonsAttributes ) )

		# Likewise, turning off subdivide polygons should fail.

		polygonMeshObject = r.object( "polygonMesh2", polygonMesh, subdividePolygonsAttributes )
		self.assertTrue( polygonMeshObject.attributes( subdividePolygonsAttributes ) )
		self.assertFalse( polygonMeshObject.attributes( defaultAttributes ) )

		# Subdivision mesh
		##################

		# No-op attribute edit should succeed.

		subdivMeshObject = r.object( "subdivMesh", subdivMesh, defaultAttributes )
		self.assertTrue( subdivMeshObject.attributes( defaultAttributes ) )
		self.assertTrue( subdivMeshObject.attributes( defaultIterationsAttributes ) )

		# Turning on subdivide polygons should succeed, because we're already
		# subdividing anyway.

		self.assertTrue( subdivMeshObject.attributes( subdividePolygonsAttributes ) )

		# But changing iterations should fail, because then we're changing the
		# geometry.

		self.assertFalse( subdivMeshObject.attributes( nonDefaultIterationsAttributes ) )

		del defaultAttributes, defaultIterationsAttributes, nonDefaultIterationsAttributes, subdividePolygonsAttributes
		del polygonMeshObject, subdivMeshObject
		del r

	def testStepSizeAttribute( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		primitives = {
			"sphere" : IECoreScene.SpherePrimitive(),
			"mesh" : IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			"curves" : IECoreScene.CurvesPrimitive.createBox( imath.Box3f( imath.V3f( -1 ), imath.V3f( 1 ) ) ),
			"volumeProcedural" : IECoreScene.ExternalProcedural(
				"volume",
				imath.Box3f( imath.V3f( -1 ), imath.V3f( 1 ) ),
			),
		}

		attributes = {
			"default" : IECore.CompoundObject(),
			"stepSizeZero" : IECore.CompoundObject( {
				"ai:shape:step_size" : IECore.FloatData( 0 ),
			} ),
			"stepSizeOne" : IECore.CompoundObject( {
				"ai:shape:step_size" : IECore.FloatData( 1 ),
			} ),
			"stepSizeTwo" : IECore.CompoundObject( {
				"ai:shape:step_size" : IECore.FloatData( 2 ),
			} )
		}

		for pn, p in primitives.items() :
			for an, a in attributes.items() :
				r.object( pn + "_" + an, p, r.attributes( a ) )

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			numInstances = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "ginstance" ] )
			numMeshes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "polymesh" ] )
			numBoxes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "box" ] )
			numSpheres = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "sphere" ] )
			numCurves = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "curves" ] )
			numVolumes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "volume" ] )

			self.assertEqual( numInstances, 16 )
			self.assertEqual( numMeshes, 3 )
			self.assertEqual( numBoxes, 0 )
			self.assertEqual( numSpheres, 3 )
			self.assertEqual( numCurves, 1 )
			self.assertEqual( numVolumes, 3 )

			self.__assertInstanced(
				"mesh_default",
				"mesh_stepSizeZero",
			)

			self.__assertInstanced(
				"sphere_default",
				"sphere_stepSizeZero",
			)

			self.__assertInstanced(
				"curves_default",
				"curves_stepSizeZero",
				"curves_stepSizeOne",
				"curves_stepSizeTwo",
			)

			for pn in primitives.keys() :
				for an, a in attributes.items() :

					instance = arnold.AiNodeLookUpByName( pn + "_" + an )
					shape = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )

					stepSize = a.get( "ai:shape:step_size" )
					stepSize = stepSize.value if stepSize is not None else 0

					if pn == "curves" :
						self.assertTrue( arnold.AiNodeIs( shape, "curves" ) )
					elif pn == "sphere" :
						self.assertTrue( arnold.AiNodeIs( shape, "sphere" ) )
						self.assertEqual( arnold.AiNodeGetFlt( shape, "step_size" ), stepSize )
					elif pn == "mesh" :
						self.assertTrue( arnold.AiNodeIs( shape, "polymesh" ) )
						self.assertEqual( arnold.AiNodeGetFlt( shape, "step_size" ), stepSize )
					elif pn == "volumeProcedural" :
						self.assertTrue( arnold.AiNodeIs( shape, "volume" ) )
						self.assertEqual( arnold.AiNodeGetFlt( shape, "step_size" ), stepSize )

	def testVolumePaddingAttribute( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		primitives = {
			"sphere" : IECoreScene.SpherePrimitive(),
			"mesh" : IECoreScene.MeshPrimitive.createPlane( imath.Box2f( imath.V2f( -1 ), imath.V2f( 1 ) ) ),
			"curves" : IECoreScene.CurvesPrimitive.createBox( imath.Box3f( imath.V3f( -1 ), imath.V3f( 1 ) ) ),
			"volumeProcedural" : IECoreScene.ExternalProcedural(
				"volume",
				imath.Box3f( imath.V3f( -1 ), imath.V3f( 1 ) ),
			),
		}

		attributes = {
			"default" : IECore.CompoundObject(),
			"volumePaddingZero" : IECore.CompoundObject( {
				"ai:shape:volume_padding" : IECore.FloatData( 0 ),
			} ),
			"volumePaddingOne" : IECore.CompoundObject( {
				"ai:shape:volume_padding" : IECore.FloatData( 1 ),
			} ),
			"volumePaddingTwo" : IECore.CompoundObject( {
				"ai:shape:volume_padding" : IECore.FloatData( 2 ),
			} )
		}

		for pn, p in primitives.items() :
			for an, a in attributes.items() :
				r.object( pn + "_" + an, p, r.attributes( a ) )

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			numInstances = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "ginstance" ] )
			numMeshes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "polymesh" ] )
			numBoxes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "box" ] )
			numSpheres = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "sphere" ] )
			numCurves = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "curves" ] )
			numVolumes = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "volume" ] )

			self.assertEqual( numInstances, 16 )
			self.assertEqual( numMeshes, 3 )
			self.assertEqual( numBoxes, 0 )
			self.assertEqual( numSpheres, 3 )
			self.assertEqual( numCurves, 1 )
			self.assertEqual( numVolumes, 3 )

			self.__assertInstanced(
				"mesh_default",
				"mesh_volumePaddingZero",
			)

			self.__assertInstanced(
				"sphere_default",
				"sphere_volumePaddingZero",
			)

			self.__assertInstanced(
				"curves_default",
				"curves_volumePaddingZero",
				"curves_volumePaddingOne",
				"curves_volumePaddingTwo",
			)

			for pn in primitives.keys() :
				for an, a in attributes.items() :

					instance = arnold.AiNodeLookUpByName( pn + "_" + an )
					shape = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )

					volumePadding = a.get( "ai:shape:volume_padding" )
					volumePadding = volumePadding.value if volumePadding is not None else 0

					if pn == "curves" :
						self.assertTrue( arnold.AiNodeIs( shape, "curves" ) )
					elif pn == "sphere" :
						self.assertTrue( arnold.AiNodeIs( shape, "sphere" ) )
						self.assertEqual( arnold.AiNodeGetFlt( shape, "volume_padding" ), volumePadding )
					elif pn == "mesh" :
						self.assertTrue( arnold.AiNodeIs( shape, "polymesh" ) )
						self.assertEqual( arnold.AiNodeGetFlt( shape, "volume_padding" ), volumePadding )
					elif pn == "volumeProcedural" :
						self.assertTrue( arnold.AiNodeIs( shape, "volume" ) )
						self.assertEqual( arnold.AiNodeGetFlt( shape, "volume_padding" ), volumePadding )

	def testStepSizeAttributeDefersToProceduralParameter( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.object(

			"test",

			IECoreScene.ExternalProcedural(
				"volume",
				imath.Box3f( imath.V3f( -1 ), imath.V3f( 1 ) ),
				IECore.CompoundData( {
					"ai:nodeType" : "volume",
					"step_size" : 0.25,
				} )
			),

			r.attributes( IECore.CompoundObject( {
				"ai:shape:step_size" : IECore.FloatData( 10.0 ),
			} ) )

		)

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

			instance = arnold.AiNodeLookUpByName( "test" )
			self.assertTrue( arnold.AiNodeIs( instance, "ginstance" ) )

			shape = arnold.AtNode.from_address( arnold.AiNodeGetPtr( instance, "node" ) )
			self.assertTrue( arnold.AiNodeIs( shape, "volume" ) )
			self.assertEqual( arnold.AiNodeGetFlt( shape, "step_size" ), 0.25 )

	def testDeclaringCustomOptions( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.option( "ai:declare:myCustomOption", IECore.StringData( "myCustomOptionValue" ) )

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )
			options = arnold.AiUniverseGetOptions()

			self.assertEqual( arnold.AiNodeGetStr( options, "myCustomOption" ), "myCustomOptionValue" )

	def testFrameAndAASeed( self ) :

		for frame in ( None, 1, 2 ) :
			for seed in ( None, 3, 4 ) :

				r = GafferScene.Private.IECoreScenePreview.Renderer.create(
					"Arnold",
					GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
					self.temporaryDirectory() + "/test.ass"
				)

				if frame is not None :
					r.option( "frame", IECore.IntData( frame ) )
				if seed is not None :
					r.option( "ai:AA_seed", IECore.IntData( seed ) )

				r.render()
				del r

				with IECoreArnold.UniverseBlock( writable = True ) :

					arnold.AiASSLoad( self.temporaryDirectory() + "/test.ass" )

					options = arnold.AiUniverseGetOptions()
					self.assertEqual(
						arnold.AiNodeGetInt( options, "AA_seed" ),
						seed or frame or 1
					)

	def testLogDirectoryCreation( self ) :

		# Directory for log file should be made automatically if
		# it doesn't exist.

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			self.temporaryDirectory() + "/test.ass"
		)

		r.option( "ai:log:filename", IECore.StringData( self.temporaryDirectory() + "/test/log.txt" ) )
		r.render()

		self.assertTrue( os.path.isdir( self.temporaryDirectory() + "/test" ) )

		# And it should still be OK to pass a filename where the directory already exists

		r.option( "ai:log:filename", IECore.StringData( self.temporaryDirectory() + "/log.txt" ) )
		r.render()

		self.assertTrue( os.path.isdir( self.temporaryDirectory() ) )

		# Passing an empty filename should be fine too.

		r.option( "ai:log:filename", IECore.StringData( "" ) )
		r.render()

		# Trying to write to a read-only location should result in an
		# error message.

		os.makedirs( self.temporaryDirectory() + "/readOnly" )
		os.chmod( self.temporaryDirectory() + "/readOnly", 444 )

		with IECore.CapturingMessageHandler() as mh :
			r.option( "ai:log:filename", IECore.StringData( self.temporaryDirectory() + "/readOnly/nested/log.txt" ) )
			r.render()

		self.assertEqual( len( mh.messages ), 1 )
		self.assertEqual( mh.messages[0].level, IECore.Msg.Level.Error )
		self.assertTrue( "Permission denied" in mh.messages[0].message )

	def testProcedural( self ) :

		class SphereProcedural( GafferScene.Private.IECoreScenePreview.Procedural ) :

			def render( self, renderer ) :

				for i in range( 0, 5 ) :
					o = renderer.object(
						"/sphere{0}".format( i ),
						IECoreScene.SpherePrimitive(),
						renderer.attributes( IECore.CompoundObject() ),
					)
					o.transform( imath.M44f().translate( imath.V3f( i, 0, 0 ) ) )

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.Batch,
		)

		r.output(
			"test",
			IECoreScene.Output(
				self.temporaryDirectory() + "/beauty.exr",
				"exr",
				"rgba",
				{
				}
			)
		)

		r.object( "/sphere", IECoreScene.SpherePrimitive(), r.attributes( IECore.CompoundObject() ) )
		r.object( "/procedural", SphereProcedural(), r.attributes( IECore.CompoundObject() ) )

		procedurals = self.__allNodes( nodeEntryName = "procedural" )
		self.assertEqual( len( procedurals ), 1 )

		r.render()

		for i in range( 0, 5 ) :
			# Look for spheres of the correct types parented under the procedural
			sphere = arnold.AiNodeLookUpByName( "/sphere%i" % i, procedurals[0] )
			# We actually expect the node to be a ginstance, but during `render()` Arnold seems
			# to switch the type of ginstances to match the type of the node they are instancing.
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( sphere ) ), "sphere" )

		# We expect to find 8 "spheres" - the 6 ginstances masquerading
		# as spheres (1 from the top level sphere, 5 from the procedural),
		# and the two true spheres that they reference.
		spheres = self.__allNodes( nodeEntryName = "sphere" )
		self.assertEqual( len( spheres ), 8 )
		# Use node names to distinguish the true spheres.
		trueSpheres = [ x for x in spheres if "sphere" not in arnold.AiNodeGetName( x ) ]
		self.assertEqual( len( trueSpheres ), 2 )
		# Check they both have names
		self.assertTrue( all( [ arnold.AiNodeGetName( x ) for x in trueSpheres ] ) )

	@staticmethod
	def __aovShaders() :

		options = arnold.AiUniverseGetOptions()
		shaders = arnold.AiNodeGetArray( options, "aov_shaders" )

		result = {}
		for i in range( arnold.AiArrayGetNumElements( shaders ) ):
			node = arnold.cast( arnold.AiArrayGetPtr( shaders, i ), arnold.POINTER( arnold.AtNode ) )
			nodeType = arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( node ) )
			result[nodeType] = node

		return result

	def testAOVShaders( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.Interactive
		)

		r.option( "ai:aov_shader:test", IECore.ObjectVector( [
			IECoreScene.Shader( "float_to_rgb", "ai:shader", { "__handle":IECore.StringData( "rgbSource" ) } ),
			IECoreScene.Shader( "aov_write_rgb", "ai:shader", { "aov_input":IECore.StringData( "link:rgbSource" ) } ),
		] ) )

		self.assertEqual( self.__aovShaders().keys(), [ "aov_write_rgb" ] )
		source = arnold.AiNodeGetLink( self.__aovShaders()["aov_write_rgb"], "aov_input" )
		self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( source ) ), "float_to_rgb" )

		# Add another
		r.option( "ai:aov_shader:test2", IECore.ObjectVector( [ IECoreScene.Shader( "aov_write_float", "ai:shader" ) ] ) )
		self.assertEqual( set( self.__aovShaders().keys() ), set( [ "aov_write_rgb", "aov_write_float" ] ) )

		# Add overwrite
		r.option( "ai:aov_shader:test", IECore.ObjectVector( [ IECoreScene.Shader( "aov_write_int", "ai:shader" ) ] ) )
		self.assertEqual( set( self.__aovShaders().keys() ), set( [ "aov_write_int", "aov_write_float" ] ) )

		r.option( "ai:aov_shader:test", None )
		self.assertEqual( self.__aovShaders().keys(), [ "aov_write_float" ] )

		r.option( "ai:aov_shader:test2", None )
		self.assertEqual( self.__aovShaders().keys(), [] )

		del r

	def testAtmosphere( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.Interactive
		)

		options = arnold.AiUniverseGetOptions()
		self.assertEqual( arnold.AiNodeGetPtr( options, "atmosphere" ), None )

		r.option(
			"ai:atmosphere",
			IECore.ObjectVector( [ IECoreScene.Shader( "atmosphere_volume", "ai:shader" ) ] )
		)

		shader = arnold.AtNode.from_address( arnold.AiNodeGetPtr( options, "atmosphere" ) )
		self.assertEqual(
			arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( shader ) ),
			"atmosphere_volume",
		)

		r.option( "ai:atmosphere", None )
		self.assertEqual( arnold.AiNodeGetPtr( options, "atmosphere" ), None )

	def testBackground( self ) :

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.Interactive
		)

		options = arnold.AiUniverseGetOptions()
		self.assertEqual( arnold.AiNodeGetPtr( options, "background" ), None )

		r.option(
			"ai:background",
			IECore.ObjectVector( [ IECoreScene.Shader( "flat", "ai:shader" ) ] )
		)

		shader = arnold.AtNode.from_address( arnold.AiNodeGetPtr( options, "background" ) )
		self.assertEqual(
			arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( shader ) ),
			"flat",
		)

		r.option( "ai:background", None )
		self.assertEqual( arnold.AiNodeGetPtr( options, "background" ), None )

	def testVDBs( self ) :

		import IECoreVDB

		tmpFile = self.temporaryDirectory() + "/test.ass"

		r = GafferScene.Private.IECoreScenePreview.Renderer.create(
			"Arnold",
			GafferScene.Private.IECoreScenePreview.Renderer.RenderType.SceneDescription,
			tmpFile
		)

		attributes = IECore.CompoundObject( {
			"ai:volume:velocity_scale" : IECore.FloatData( 10 ),
			"ai:volume:velocity_fps" : IECore.FloatData( 25 ),
			"ai:volume:velocity_outlier_threshold" : IECore.FloatData( 0.5 ) } )

		# Camera needs to be added first as it's being used for translating the VDB.
		# We are doing the same when translating actual Gaffer scenes here:
		# https://github.com/GafferHQ/gaffer/blob/master/src/GafferScene/Render.cpp#L254
		r.camera(
			"testCamera",
			IECoreScene.Camera(
				parameters = {
					"shutter" : imath.V2f( 10.75, 11.25 )
				}
			),
			r.attributes( IECore.CompoundObject() )
		)

		r.object( "test_vdb", IECoreVDB.VDBObject(), r.attributes( attributes ) )

		r.option( "camera", IECore.StringData( "testCamera" ) )

		r.render()
		del r

		with IECoreArnold.UniverseBlock( writable = True ) :

			arnold.AiASSLoad( tmpFile )

			shapes = self.__allNodes( type = arnold.AI_NODE_SHAPE )
			numInstances = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "ginstance" ] )
			numVDBs = len( [ s for s in shapes if arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( s ) ) == "volume" ] )

			self.assertEqual( len( shapes ), 2 )
			self.assertEqual( numInstances, 1 )
			self.assertEqual( numVDBs, 1 )

			vdbInstance = arnold.AiNodeLookUpByName( "test_vdb" )
			vdbShape = arnold.AtNode.from_address( arnold.AiNodeGetPtr( vdbInstance, "node" ) )

			self.assertEqual( arnold.AiNodeGetFlt( vdbShape, "velocity_scale" ), 10 )
			self.assertEqual( arnold.AiNodeGetFlt( vdbShape, "velocity_fps" ), 25 )
			self.assertEqual( arnold.AiNodeGetFlt( vdbShape, "velocity_outlier_threshold" ), 0.5 )

			# make sure motion_start and motion_end parameters were set according to the active camera's shutter
			self.assertEqual( arnold.AiNodeGetFlt( vdbShape, "motion_start" ), 10.75 )
			self.assertEqual( arnold.AiNodeGetFlt( vdbShape, "motion_end" ), 11.25 )

	@staticmethod
	def __m44f( m ) :

		return imath.M44f( *[ i for row in m.data for i in row ] )

	def __allNodes( self, type = arnold.AI_NODE_ALL, ignoreBuiltIn = True, nodeEntryName = None ) :

		result = []
		i = arnold.AiUniverseGetNodeIterator( type )
		while not arnold.AiNodeIteratorFinished( i ) :
			node = arnold.AiNodeIteratorGetNext( i )
			if ignoreBuiltIn and arnold.AiNodeGetName( node ) in ( "root", "ai_default_reflection_shader" ) :
				continue
			if nodeEntryName is not None and arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( node ) ) != nodeEntryName :
				continue
			result.append( node )

		return result

	def __assertInstanced( self, *names ) :

		firstInstanceNode = arnold.AiNodeLookUpByName( names[0] )
		for name in names :

			instanceNode = arnold.AiNodeLookUpByName( name )
			self.assertEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( instanceNode ) ), "ginstance" )

			nodePtr = arnold.AiNodeGetPtr( instanceNode, "node" )
			self.assertEqual( nodePtr, arnold.AiNodeGetPtr( firstInstanceNode, "node" ) )
			self.assertEqual( arnold.AiNodeGetByte( arnold.AtNode.from_address( nodePtr ), "visibility" ), 0 )

	def __assertNotInstanced( self, *names ) :

		for name in names :
			node = arnold.AiNodeLookUpByName( name )
			self.assertNotEqual( arnold.AiNodeEntryGetName( arnold.AiNodeGetNodeEntry( node ) ), "ginstance" )

if __name__ == "__main__":
	unittest.main()
